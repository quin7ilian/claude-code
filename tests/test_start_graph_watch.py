from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import start_graph_watch  # noqa: E402
from start_graph_watch import (  # noqa: E402
    FAILED,
    NO_GRAPH,
    READY,
    ensure,
    is_watcher,
    state_file,
)


CLI = "/opt/tools/bin/code-review-graph"
INTERPRETER = "/opt/tools/venv/bin/python"


class FakeProcessTable:
    """A stand-in /proc, so the real cmdline parsing is exercised rather than mocked out."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, pid: int, arguments: list[str]) -> None:
        directory = self.root / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        # A real cmdline is NUL-separated and NUL-terminated.
        payload = b"".join(argument.encode() + b"\0" for argument in arguments)
        (directory / "cmdline").write_bytes(payload)


class CliRecorder:
    """Stands in for the CLI subprocess calls: records them, answers per subcommand."""

    def __init__(self, results: dict[str, bool]) -> None:
        self.calls: list[list[str]] = []
        self.results = results

    def __call__(self, executable: str, arguments: list[str]) -> bool:
        self.calls.append(arguments)
        return self.results.get(arguments[0], True)


class PopenRecorder:
    """Stands in for `subprocess.Popen`, so how a process is launched can be asserted
    without launching one."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **keywords):  # noqa: ANN001
        self.calls.append((list(command), keywords))
        return types.SimpleNamespace(pid=self.pid)


class SpawnRecorder:
    def __init__(self, pid: int | None) -> None:
        self.pid = pid
        self.calls: list[dict] = []

    def __call__(
        self, executable: str, repo: Path, log_path: Path, embeddings: bool
    ) -> int | None:
        self.calls.append({"repo": repo, "log_path": log_path, "embeddings": embeddings})
        return self.pid


class GraphWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "org" / "repo"
        self.repo.mkdir(parents=True)
        self.state_dir = self.root / "graph-watch"
        self.processes = FakeProcessTable(self.root / "proc")

    # -- fixtures ---------------------------------------------------------------

    def build_graph(self, repo: Path | None = None) -> None:
        graph_directory = (repo or self.repo) / ".code-review-graph"
        graph_directory.mkdir(parents=True, exist_ok=True)
        (graph_directory / "graph.db").write_bytes(b"")

    def record_watcher_pid(self, pid: int) -> Path:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        pid_path = state_file(self.state_dir, self.repo, "pid")
        pid_path.write_text(f"{pid}\n", encoding="utf-8")
        return pid_path

    def watcher_command_line(self, repo: Path | None = None) -> list[str]:
        """A console script's cmdline: interpreter first, the script itself second."""
        return [INTERPRETER, CLI, "watch", "--repo", str(repo or self.repo)]

    def run_ensure(
        self,
        *,
        executable: str | None = CLI,
        cli_results: dict[str, bool] | None = None,
        spawn_pid: int | None = None,
    ) -> tuple[str, CliRecorder, SpawnRecorder]:
        recorder = CliRecorder(cli_results or {})
        spawner = SpawnRecorder(spawn_pid)
        with ExitStack() as stack:
            for attribute, replacement in (
                ("PROC_ROOT", self.processes.root),
                ("cli_executable", lambda: executable),
                ("run_cli", recorder),
                ("spawn_watcher", spawner),
            ):
                stack.enter_context(
                    mock.patch.object(start_graph_watch, attribute, replacement)
                )
            result = ensure(self.repo, self.state_dir)
        return result, recorder, spawner

    def run_main(self, args: argparse.Namespace, stdin: str = "") -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(start_graph_watch, "parse_args", lambda: args))
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(stdin)))
            stack.enter_context(mock.patch.object(sys, "stdout", stdout))
            stack.enter_context(mock.patch.object(sys, "stderr", stderr))
            status = start_graph_watch.main()
        return status, stdout.getvalue(), stderr.getvalue()

    # -- the ensure sequence ----------------------------------------------------

    def test_repository_without_a_graph_is_left_alone(self) -> None:
        result, recorder, spawner = self.run_ensure()

        self.assertEqual(result, NO_GRAPH)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(spawner.calls, [])
        # Nothing is created for a repository that opted out of a graph.
        self.assertFalse(self.state_dir.exists())

    def test_live_watcher_means_the_graph_needs_no_catch_up(self) -> None:
        self.build_graph()
        self.record_watcher_pid(4321)
        self.processes.add(4321, self.watcher_command_line())

        result, recorder, spawner = self.run_ensure()

        self.assertEqual(result, READY)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(spawner.calls, [])

    def test_dead_pid_gets_a_catch_up_then_a_fresh_watcher(self) -> None:
        self.build_graph()
        pid_path = self.record_watcher_pid(4321)  # no /proc entry: the watcher is gone
        self.processes.add(5555, self.watcher_command_line())

        result, recorder, spawner = self.run_ensure(spawn_pid=5555)

        self.assertEqual(result, READY)
        # A watcher that was down missed every change made while it was gone, and a file
        # saved during the catch-up predates the new watcher's subscription — the closing
        # update, run with the watcher live, is what covers it.
        self.assertEqual(
            recorder.calls,
            [
                ["update", "-q", "--repo", str(self.repo)],
                ["embed", "--repo", str(self.repo)],
                [
                    "update",
                    "-q",
                    "--repo",
                    str(self.repo),
                    *start_graph_watch.EMBEDDING_ARGUMENTS,
                ],
            ],
        )
        self.assertEqual(len(spawner.calls), 1)
        self.assertTrue(spawner.calls[0]["embeddings"])
        self.assertEqual(spawner.calls[0]["repo"], self.repo)
        self.assertEqual(pid_path.read_text(encoding="utf-8").strip(), "5555")

    def test_recycled_pid_running_something_else_is_not_the_watcher(self) -> None:
        self.build_graph()
        self.record_watcher_pid(4321)
        self.processes.add(4321, ["/usr/bin/tail", "-f", "/var/log/example.log"])
        self.processes.add(5555, self.watcher_command_line())

        result, recorder, spawner = self.run_ensure(spawn_pid=5555)

        self.assertEqual(result, READY)
        self.assertEqual(len(spawner.calls), 1)
        self.assertEqual(len(recorder.calls), 3)

    def test_watcher_of_another_repository_does_not_count_as_this_one(self) -> None:
        self.build_graph()
        other_repo = self.root / "org" / "other"
        other_repo.mkdir(parents=True)
        self.record_watcher_pid(4321)
        self.processes.add(4321, self.watcher_command_line(repo=other_repo))
        self.processes.add(5555, self.watcher_command_line())

        result, _, spawner = self.run_ensure(spawn_pid=5555)

        self.assertEqual(result, READY)
        self.assertEqual(len(spawner.calls), 1)

    def test_is_watcher_checks_the_cli_the_subcommand_and_the_repository(self) -> None:
        self.assertTrue(is_watcher(self.watcher_command_line(), self.repo))
        # No interpreter prefix: a directly executed binary is the same watcher.
        self.assertTrue(is_watcher([CLI, "watch", "--repo", str(self.repo)], self.repo))
        self.assertFalse(
            is_watcher([INTERPRETER, CLI, "update", "--repo", str(self.repo)], self.repo)
        )
        self.assertFalse(is_watcher([INTERPRETER, CLI, "watch"], self.repo))
        self.assertFalse(is_watcher(["/usr/bin/watch", "--repo", str(self.repo)], self.repo))
        # A dangling `--repo` cannot read past the end of the vector.
        self.assertFalse(is_watcher([CLI, "watch", "--repo"], self.repo))

    def test_a_read_only_search_for_the_word_watch_is_not_the_watcher(self) -> None:
        """`search` takes a positional query, so `search watch --repo <repo>` is a legal
        read-only command against this very repository. Recycled onto the recorded pid it
        would otherwise pass for the watcher, and a graph nobody maintains would be
        reported current."""
        self.assertFalse(
            is_watcher(
                [INTERPRETER, CLI, "search", "watch", "--repo", str(self.repo)], self.repo
            )
        )

    def test_failed_embed_costs_the_watcher_its_flags_but_not_its_existence(self) -> None:
        self.build_graph()
        self.processes.add(5555, self.watcher_command_line())

        result, recorder, spawner = self.run_ensure(
            cli_results={"embed": False}, spawn_pid=5555
        )

        self.assertEqual(result, READY)
        self.assertEqual(recorder.calls[0][0], "update")
        self.assertEqual(len(spawner.calls), 1)
        self.assertFalse(spawner.calls[0]["embeddings"])
        # The closing update matches the watcher: no embedding flags either.
        self.assertEqual(recorder.calls[-1], ["update", "-q", "--repo", str(self.repo)])

    def test_failed_catch_up_starts_nothing_and_fails(self) -> None:
        self.build_graph()

        result, recorder, spawner = self.run_ensure(cli_results={"update": False})

        self.assertEqual(result, FAILED)
        self.assertEqual(recorder.calls, [["update", "-q", "--repo", str(self.repo)]])
        self.assertEqual(spawner.calls, [])

    def test_graph_present_without_the_cli_is_a_failure(self) -> None:
        self.build_graph()

        result, recorder, spawner = self.run_ensure(executable=None)

        self.assertEqual(result, FAILED)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(spawner.calls, [])

    def test_watcher_that_did_not_come_up_is_never_reported_ready(self) -> None:
        self.build_graph()
        # Spawned, but absent from the process table: it exited immediately.
        result, _, spawner = self.run_ensure(spawn_pid=5555)
        self.assertEqual(result, FAILED)
        self.assertEqual(len(spawner.calls), 1)

        # Nothing spawned at all.
        result, _, _ = self.run_ensure(spawn_pid=None)
        self.assertEqual(result, FAILED)

    def test_a_pid_that_cannot_be_recorded_launches_no_watcher(self) -> None:
        """A watcher whose pid could not be recorded would keep running unseen, and the
        next ensure — finding no usable pid — would start a second writer beside it. So
        the record is opened before anything is launched."""
        self.build_graph()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state_file(self.state_dir, self.repo, "pid").mkdir()

        result, recorder, spawner = self.run_ensure(spawn_pid=5555)

        self.assertEqual(result, FAILED)
        self.assertEqual(spawner.calls, [])
        self.assertEqual(recorder.calls, [])

    def test_state_files_stay_owner_only_whatever_the_umask_or_the_old_mode(self) -> None:
        self.build_graph()
        self.processes.add(5555, self.watcher_command_line())
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o777)
        stale_lock = state_file(self.state_dir, self.repo, "lock")
        stale_lock.write_text("", encoding="utf-8")
        os.chmod(stale_lock, 0o666)

        previous = os.umask(0o777)
        try:
            result, _, _ = self.run_ensure(spawn_pid=5555)
        finally:
            os.umask(previous)

        self.assertEqual(result, READY)
        self.assertEqual(stat.S_IMODE(self.state_dir.stat().st_mode), 0o700)
        for suffix in ("lock", "pid"):
            path = state_file(self.state_dir, self.repo, suffix)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, suffix)

    def test_state_files_carry_ids_at_owner_only_permissions(self) -> None:
        self.build_graph()
        self.processes.add(5555, self.watcher_command_line())

        self.run_ensure(spawn_pid=5555)

        pid_path = state_file(self.state_dir, self.repo, "pid")
        self.assertEqual(stat.S_IMODE(self.state_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(pid_path.stat().st_mode), 0o600)
        self.assertEqual(pid_path.read_text(encoding="utf-8").strip(), "5555")
        # File names identify a repository without spelling it out.
        self.assertNotIn("repo", pid_path.name)

    def test_a_second_ensure_waits_for_the_one_already_running(self) -> None:
        """The lock is what keeps two writers off one graph: with it held, an ensure makes
        no progress at all until it is released."""
        self.build_graph()
        self.processes.add(5555, self.watcher_command_line())
        self.state_dir.mkdir(parents=True, exist_ok=True)
        held = os.open(
            state_file(self.state_dir, self.repo, "lock"), os.O_CREAT | os.O_RDWR, 0o600
        )
        fcntl.flock(held, fcntl.LOCK_EX)
        outcome: list[str] = []
        worker = threading.Thread(
            target=lambda: outcome.append(self.run_ensure(spawn_pid=5555)[0])
        )
        worker.start()
        try:
            worker.join(timeout=0.5)
            self.assertTrue(worker.is_alive())
            self.assertEqual(outcome, [])
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
            os.close(held)
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, [READY])

    # -- how the processes are launched -----------------------------------------

    def test_watcher_is_launched_detached_into_its_own_log(self) -> None:
        log_path = self.state_dir / "watch.log"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        recorder = PopenRecorder()

        with mock.patch.object(start_graph_watch.subprocess, "Popen", recorder):
            pid = start_graph_watch.spawn_watcher(CLI, self.repo, log_path, True)

        self.assertEqual(pid, recorder.pid)
        command, keywords = recorder.calls[0]
        self.assertEqual(
            command,
            [
                CLI,
                "watch",
                "--repo",
                str(self.repo),
                "--embedding-provider",
                "local",
                "--embedding-model",
                "all-MiniLM-L6-v2",
            ],
        )
        # Its own session: the watcher outlives the session that started it and survives a
        # kill aimed at that session's process group.
        self.assertIs(keywords["start_new_session"], True)
        self.assertEqual(keywords["stdin"], subprocess.DEVNULL)
        self.assertEqual(keywords["stderr"], subprocess.STDOUT)
        self.assertEqual(keywords["cwd"], str(self.repo))
        # Output lands in the per-repo log, and its descriptor is not left open here.
        self.assertIsInstance(keywords["stdout"], int)
        with self.assertRaises(OSError):
            os.fstat(keywords["stdout"])
        self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)

    def test_watcher_log_is_owner_only_and_appended_to(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        log_path = state_file(self.state_dir, self.repo, "log")
        log_path.write_text("earlier watcher output\n", encoding="utf-8")
        os.chmod(log_path, 0o666)
        recorder = PopenRecorder()

        previous = os.umask(0o777)
        try:
            with mock.patch.object(start_graph_watch.subprocess, "Popen", recorder):
                start_graph_watch.spawn_watcher(CLI, self.repo, log_path, True)
        finally:
            os.umask(previous)

        self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o600)
        self.assertEqual(log_path.read_text(encoding="utf-8"), "earlier watcher output\n")

    def test_watcher_without_an_embedding_index_keeps_running_minus_the_flags(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        recorder = PopenRecorder()

        with mock.patch.object(start_graph_watch.subprocess, "Popen", recorder):
            start_graph_watch.spawn_watcher(CLI, self.repo, self.state_dir / "w.log", False)

        self.assertEqual(recorder.calls[0][0], [CLI, "watch", "--repo", str(self.repo)])

    def test_hook_launches_the_sequence_detached_and_holds_no_session_stream(self) -> None:
        recorder = PopenRecorder()

        with mock.patch.object(start_graph_watch.subprocess, "Popen", recorder):
            start_graph_watch.spawn_ensure(self.repo, self.state_dir)

        command, keywords = recorder.calls[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(Path(command[1]).name, "start_graph_watch.py")
        self.assertEqual(
            command[2:],
            ["--repo", str(self.repo), "--sync", "--state-dir", str(self.state_dir)],
        )
        self.assertIs(keywords["start_new_session"], True)
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(keywords[stream], subprocess.DEVNULL)

    # -- the two entry points ---------------------------------------------------

    def test_the_parser_reads_the_wired_invocations(self) -> None:
        """The two command lines this script is installed behind: the SessionStart hook
        entry, and the detached child the hook itself starts."""
        with mock.patch.object(sys, "argv", ["start_graph_watch.py"]):
            hook_args = start_graph_watch.parse_args()
        self.assertFalse(hook_args.sync)
        self.assertIsNone(hook_args.repo)
        self.assertEqual(
            hook_args.state_dir, Path(start_graph_watch.DEFAULT_STATE_DIR).expanduser()
        )

        with mock.patch.object(
            sys,
            "argv",
            [
                "start_graph_watch.py",
                "--repo",
                str(self.repo),
                "--sync",
                "--state-dir",
                str(self.state_dir),
            ],
        ):
            sync_args = start_graph_watch.parse_args()
        self.assertTrue(sync_args.sync)
        self.assertEqual(sync_args.repo, self.repo)
        self.assertEqual(sync_args.state_dir, self.state_dir)

    def test_sync_exit_codes_separate_no_graph_from_a_failed_ensure(self) -> None:
        args = argparse.Namespace(repo=self.repo, sync=True, state_dir=self.state_dir)

        with mock.patch.object(start_graph_watch, "ensure", lambda *a: NO_GRAPH):
            status, stdout, stderr = self.run_main(args)
        self.assertEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")

        with mock.patch.object(start_graph_watch, "ensure", lambda *a: READY):
            status, stdout, _ = self.run_main(args)
        self.assertEqual(status, 0)
        self.assertEqual(stdout, "")

        with mock.patch.object(start_graph_watch, "ensure", lambda *a: FAILED):
            status, stdout, stderr = self.run_main(args)
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(len(stderr.strip().splitlines()), 1)

        # An ensure that raises is a failure, not a traceback.
        def raising(*args_: object) -> str:
            raise RuntimeError("boom")

        with mock.patch.object(start_graph_watch, "ensure", raising):
            status, stdout, stderr = self.run_main(args)
        self.assertNotEqual(status, 0)
        self.assertEqual(stdout, "")

    def test_sync_over_a_real_repository_without_a_graph_exits_zero(self) -> None:
        args = argparse.Namespace(repo=self.repo, sync=True, state_dir=self.state_dir)

        with mock.patch.object(start_graph_watch, "cli_executable", lambda: CLI):
            status, stdout, stderr = self.run_main(args)

        self.assertEqual(status, 0)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")

    def test_hook_spawns_the_sequence_only_where_a_graph_exists(self) -> None:
        (self.repo / ".git").mkdir()
        nested = self.repo / "src" / "deep"
        nested.mkdir(parents=True)
        spawned: list[tuple[Path, Path]] = []
        args = argparse.Namespace(repo=None, sync=False, state_dir=self.state_dir)
        hook_input = json.dumps({"hook_event_name": "SessionStart", "cwd": str(nested)})

        with mock.patch.object(
            start_graph_watch, "spawn_ensure", lambda repo, state: spawned.append((repo, state))
        ):
            status, stdout, stderr = self.run_main(args, stdin=hook_input)
            self.assertEqual((status, stdout, stderr), (0, "", ""))
            self.assertEqual(spawned, [])

            self.build_graph()
            status, stdout, stderr = self.run_main(args, stdin=hook_input)

        self.assertEqual((status, stdout, stderr), (0, "", ""))
        # Resolved to the repository root, not the working directory inside it.
        self.assertEqual(spawned, [(self.repo, self.state_dir)])

    def test_hook_is_silent_and_harmless_on_malformed_input(self) -> None:
        self.build_graph()
        (self.repo / ".git").mkdir()
        spawned: list[tuple[Path, Path]] = []
        args = argparse.Namespace(repo=None, sync=False, state_dir=self.state_dir)
        payloads = (
            "",
            "not json at all",
            "[]",
            '"a string"',
            "{}",
            json.dumps({"hook_event_name": "Stop", "cwd": "/does/not/matter"}),
            json.dumps({"hook_event_name": "SessionStart"}),
            json.dumps({"hook_event_name": "SessionStart", "cwd": 17}),
            json.dumps({"hook_event_name": "SessionStart", "cwd": ""}),
            json.dumps({"hook_event_name": "SessionStart", "cwd": "/nonexistent/xyz"}),
        )

        with mock.patch.object(
            start_graph_watch, "spawn_ensure", lambda repo, state: spawned.append((repo, state))
        ):
            for payload in payloads:
                with self.subTest(payload=payload):
                    status, stdout, stderr = self.run_main(args, stdin=payload)
                    self.assertEqual(status, 0)
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, "")

        self.assertEqual(spawned, [])


class ReviewGateGraphNoteTests(unittest.TestCase):
    """The review gate's graph note is followed verbatim by a reviewer whose working
    directory is an ephemeral scratch, not the repository under review."""

    def setUp(self) -> None:
        self.gate = (Path(__file__).resolve().parents[1] / "bin" / "codex-review").read_text(
            encoding="utf-8"
        )

    def test_every_graph_command_names_the_repository(self) -> None:
        # `code-review-graph` resolves its repository from the working directory, so a
        # command without --repo reads the scratch and answers from an empty graph.
        for match in re.finditer(r"code-review-graph ([a-z-]+)", self.gate):
            following = self.gate[match.end() : match.end() + 8]
            self.assertEqual(following, " --repo ", f"{match.group(0)} is missing --repo")

    def test_the_repository_placeholder_is_substituted_before_use(self) -> None:
        self.assertIn("__REPO__", self.gate)
        self.assertRegex(self.gate, r"__REPO__/\$REPO")


if __name__ == "__main__":
    unittest.main()
