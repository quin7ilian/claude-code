#!/usr/bin/env python3
"""Keep a repository's code graph current under a single background watcher.

`code-review-graph watch` is the only writer of a repository's graph: it applies file
changes and refreshes vectors within about a second, and holding the database open keeps
the WAL sidecar files alive, which is what lets sandboxed read-only queries open it at
all. Everything else — agents, the review gate, the reviewer — reads. This script is what
guarantees a watcher is running.

Two entry points share one ensure sequence:

- `SessionStart` hook: reads the hook JSON on stdin, spawns the sequence detached, prints
  nothing, and exits 0 immediately.
- `--repo <path> --sync`: runs the sequence in the foreground for the review gate, exiting
  0 only once the graph is caught up and a watcher is alive.

The sequence is serialized per repository by a flock. A repository with no graph is left
alone — building one is the user's opt-in decision, never this script's. When the recorded
watcher is alive it has been maintaining the graph and there is nothing to do. Otherwise
the graph is caught up first (`update -q`, then `embed`), because a watcher that was down
missed every change made while it was gone, and a new watcher is started in its own
session so it outlives the session that spawned it and any process-group kill. A file
saved during the catch-up itself predates the watcher's subscription, so one more update
runs once the watcher is seen alive. A failed
`embed` costs the watcher its embedding flags, never its existence: graph freshness is not
hostage to the embedding stack. The watcher is left running; nothing here stops one.

Fail-open in hook mode: every failure path prints nothing and exits 0. In `--sync` mode a
failed ensure exits non-zero with one terse line on stderr, so the review gate can omit
its graph guidance rather than describe a stale graph as current.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inject_repo_instructions import find_repo_root  # noqa: E402

DEFAULT_STATE_DIR = "~/.claude/graph-watch"
GRAPH_DATABASE = Path(".code-review-graph") / "graph.db"
CLI_NAME = "code-review-graph"
EMBEDDING_ARGUMENTS = (
    "--embedding-provider",
    "local",
    "--embedding-model",
    "all-MiniLM-L6-v2",
)
PROC_ROOT = Path("/proc")

# Ensure outcomes. A repository without a graph is a fact, not a failure: only a graph
# that is present and could not be brought under a live watcher is an error.
NO_GRAPH = "no-graph"
READY = "ready"
FAILED = "failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--sync", action="store_true")
    parser.add_argument(
        "--state-dir", type=Path, default=Path(DEFAULT_STATE_DIR).expanduser()
    )
    return parser.parse_args()


def resolved_path(text: str) -> Path | None:
    try:
        return Path(text).resolve()
    except OSError:
        return None


def cli_executable() -> str | None:
    return shutil.which(CLI_NAME)


def repository_key(repo: Path) -> str:
    """Per-repository state file name. A hash keeps the path out of the file name while
    keeping one repository's state separate from another's."""
    return hashlib.sha256(str(repo).encode()).hexdigest()


def state_file(state_dir: Path, repo: Path, suffix: str) -> Path:
    return state_dir / f"{repository_key(repo)}.{suffix}"


def prepare_state_dir(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)


def process_command_line(pid: int) -> list[str] | None:
    """The argument vector of a running process, or None when it is not running.

    A zombie carries an empty cmdline, which reads here as not running — the watcher it
    once was is no longer maintaining anything."""
    try:
        raw = (PROC_ROOT / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    arguments = [token for token in raw.decode("utf-8", "replace").split("\0") if token]
    return arguments or None


def is_watcher(arguments: list[str], repo: Path) -> bool:
    """Whether an argument vector is this repository's watcher.

    Identity, not just liveness: a recorded pid outlives the process that owned it and is
    recycled by whatever starts next — including a read-only `search watch --repo <repo>`,
    whose tokens are the watcher's own. So `watch` has to be the subcommand, the token
    directly after the CLI, and `--repo` has to name this repository after it. A console
    script's cmdline starts with its interpreter and carries the script next, so the CLI
    is looked for across the tokens rather than at argv[0]."""
    for index, token in enumerate(arguments):
        if os.path.basename(token) != CLI_NAME:
            continue
        subcommand = arguments[index + 1 :]
        if not subcommand or subcommand[0] != "watch":
            return False
        for position, argument in enumerate(subcommand[:-1]):
            if argument == "--repo" and resolved_path(subcommand[position + 1]) == repo:
                return True
        return False
    return False


def recorded_pid(pid_path: Path) -> int | None:
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    try:
        pid = int(text)
    except ValueError:
        return None
    return pid if pid > 0 else None


def open_state_file(path: Path, flags: int) -> int:
    """Open a state file owner-only. The mode passed to `open` is filtered by the umask
    and ignored outright for a file that already exists, so the permission is set on the
    descriptor rather than requested at creation."""
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except OSError:
        os.close(descriptor)
        raise
    return descriptor


def watcher_is_running(pid_path: Path, repo: Path) -> bool:
    pid = recorded_pid(pid_path)
    if pid is None:
        return False
    arguments = process_command_line(pid)
    return arguments is not None and is_watcher(arguments, repo)


def run_cli(executable: str, arguments: list[str]) -> bool:
    """Run one CLI subcommand to completion. Its output belongs to no session: the hook
    prints nothing and the review gate's stdout is the review."""
    try:
        completed = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def spawn_watcher(
    executable: str, repo: Path, log_path: Path, embeddings: bool
) -> int | None:
    """Start the watcher in its own session, logging to the state directory.

    A new session detaches it from the terminal and process group of whatever started it,
    so it survives session teardown and any group-wide kill."""
    command = [executable, "watch", "--repo", str(repo)]
    if embeddings:
        command.extend(EMBEDDING_ARGUMENTS)
    try:
        descriptor = open_state_file(log_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND)
    except OSError:
        return None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=descriptor,
            stderr=subprocess.STDOUT,
            cwd=str(repo),
            start_new_session=True,
        )
    except OSError:
        return None
    finally:
        os.close(descriptor)
    return process.pid


def ensure_locked(executable: str, repo: Path, state_dir: Path) -> str:
    pid_path = state_file(state_dir, repo, "pid")
    if watcher_is_running(pid_path, repo):
        return READY
    # The pid record is opened before anything is launched: a watcher whose pid could not
    # be recorded keeps running unseen, and the next ensure — finding no usable pid —
    # starts a second writer beside it.
    try:
        pid_descriptor = open_state_file(
            pid_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC
        )
    except OSError:
        return FAILED
    try:
        if not run_cli(executable, ["update", "-q", "--repo", str(repo)]):
            return FAILED
        embeddings = run_cli(executable, ["embed", "--repo", str(repo)])
        pid = spawn_watcher(
            executable, repo, state_file(state_dir, repo, "log"), embeddings
        )
        if pid is None:
            return FAILED
        record = f"{pid}\n".encode()
        while record:
            record = record[os.write(pid_descriptor, record) :]
    except OSError:
        return FAILED
    finally:
        os.close(pid_descriptor)
    # The watcher is claimed alive only after it has been seen alive.
    if not watcher_is_running(pid_path, repo):
        return FAILED
    # A file saved during the catch-up predates the watcher's subscription and produced
    # no event, so it is in neither. One more update with the watcher live covers it —
    # vectors included when the index is in play. A failure here leaves a live watcher
    # and at worst that same narrow gap, so the ensure still succeeds.
    closing_update = ["update", "-q", "--repo", str(repo)]
    if embeddings:
        closing_update.extend(EMBEDDING_ARGUMENTS)
    run_cli(executable, closing_update)
    return READY


def ensure(repo: Path, state_dir: Path) -> str:
    """Bring the repository's graph under a live watcher.

    Blocks on the per-repository lock rather than giving up on it: whoever holds it is
    running this same sequence, so waiting yields the result this call wants."""
    if not (repo / GRAPH_DATABASE).is_file():
        return NO_GRAPH
    executable = cli_executable()
    if executable is None:
        return FAILED
    try:
        prepare_state_dir(state_dir)
        lock_descriptor = open_state_file(
            state_file(state_dir, repo, "lock"), os.O_CREAT | os.O_RDWR
        )
    except OSError:
        return FAILED
    with os.fdopen(lock_descriptor, "r+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except OSError:
            return FAILED
        return ensure_locked(executable, repo, state_dir)


def spawn_ensure(repo: Path, state_dir: Path) -> None:
    """Run the ensure sequence detached. Its stdio is closed off so a session is never
    held open by it, and its exit status is nobody's business: a session that cannot get
    a watcher started proceeds without one."""
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--repo",
                str(repo),
                "--sync",
                "--state-dir",
                str(state_dir),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def run_sync(args: argparse.Namespace) -> int:
    if args.repo is None:
        print("start_graph_watch: --sync requires --repo", file=sys.stderr)
        return 2
    repo = resolved_path(str(args.repo))
    if repo is None or not repo.is_dir():
        print(f"start_graph_watch: not a directory: {args.repo}", file=sys.stderr)
        return 1
    try:
        result = ensure(repo, args.state_dir)
    except Exception:
        result = FAILED
    if result == FAILED:
        print(
            "start_graph_watch: no live watcher for the code graph in "
            f"{repo} — its freshness is unverified",
            file=sys.stderr,
        )
        return 1
    return 0


def run_hook(args: argparse.Namespace) -> int:
    try:
        hook_input = json.load(sys.stdin)
        if not isinstance(hook_input, dict):
            return 0
        if hook_input.get("hook_event_name") != "SessionStart":
            return 0
        cwd = hook_input.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return 0
        root = find_repo_root(Path(cwd))
        if root is None or not (root / GRAPH_DATABASE).is_file():
            return 0
        spawn_ensure(root, args.state_dir)
    except Exception:
        return 0
    return 0


def main() -> int:
    args = parse_args()
    if args.sync:
        return run_sync(args)
    return run_hook(args)


if __name__ == "__main__":
    raise SystemExit(main())
