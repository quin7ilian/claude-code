from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gate_repo_instructions import (  # noqa: E402
    DISABLE_ENV,
    evaluate,
    read_output_matches,
    stable_project,
)
from prime_hindsight import rules_path  # noqa: E402


RULES = "# AGENTS.md\n\nNever commit.\nAlways run the tests.\n"


def numbered(text: str) -> str:
    """Render text the way the Read tool does: every element of the newline split gets a
    number, so a file ending in a newline gains a final numbered-but-empty line."""
    return "\n".join(f"{i + 1}\t{line}" for i, line in enumerate(text.split("\n")))


def read_call(path: str, tool_use_id: str, **extra) -> dict:
    payload = {"file_path": path}
    payload.update(extra)
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_use_id, "name": "Read", "input": payload}
            ],
        },
    }


def read_result(tool_use_id: str, text: str, structured: bool = False) -> dict:
    record = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": numbered(text)}
            ],
        },
    }
    if structured:
        record["toolUseResult"] = {"file": {"content": numbered(text)}}
    return record


def usage_record(context_tokens: int) -> dict:
    """An assistant record reporting the context size the model held for it."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [],
            "usage": {"input_tokens": 1, "cache_read_input_tokens": context_tokens - 1},
        },
    }


def compaction_record() -> dict:
    return {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": []}}


def write_transcript(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.instructions = self.repo / "AGENTS.md"
        self.instructions.write_text(RULES, encoding="utf-8")
        self.target = self.repo / "sample.py"
        self.target.write_text("x = 1\n", encoding="utf-8")
        self.transcript = root / "session.jsonl"
        # No standing-rules document by default: that half of the gate does not apply.
        self.cache = root / "primer"
        self.cache.mkdir()
        self.env_file = root / ".env"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def hook_input(self, **extra) -> dict:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "cwd": str(self.repo),
            "transcript_path": str(self.transcript),
            "tool_input": {"file_path": str(self.target)},
        }
        payload.update(extra)
        return payload

    def rules_document(self) -> Path:
        path = rules_path(self.cache, stable_project(str(self.repo)))
        path.write_text("# standing rules\n- never commit\n", encoding="utf-8")
        return path

    def denied(self, hook_input: dict, max_growth: int = 200_000) -> bool:
        decision = evaluate(hook_input, max_growth, self.cache, self.env_file)
        if decision is None:
            return False
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
        return True

    def compliant_transcript(self, structured: bool = False) -> None:
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES, structured=structured),
            ],
        )

    # -- passing the gate -------------------------------------------------------

    def test_allows_after_a_complete_current_read(self) -> None:
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input()))

    def test_allows_a_file_with_no_trailing_newline(self) -> None:
        self.instructions.write_text("# rules\nno trailing newline", encoding="utf-8")
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_result("t1", "# rules\nno trailing newline"),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_structured_result_alongside_correlated_tool_result_passes(self) -> None:
        self.compliant_transcript(structured=True)
        self.assertFalse(self.denied(self.hook_input()))

    def test_allow_emits_no_output_so_permissions_are_untouched(self) -> None:
        self.compliant_transcript()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_repo_instructions.py")],
            input=json.dumps(self.hook_input()),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_deny_emits_a_decision_on_stdout(self) -> None:
        write_transcript(
            self.transcript,
            [read_call(str(self.target), "t1"), read_result("t1", "x = 1\n")],
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "gate_repo_instructions.py")],
            input=json.dumps(self.hook_input()),
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    # -- failing the gate -------------------------------------------------------

    def test_denies_when_the_file_was_never_read(self) -> None:
        write_transcript(
            self.transcript,
            [read_call(str(self.target), "t1"), read_result("t1", "x = 1\n")],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_denies_ranged_reads_including_zero_valued_ranges(self) -> None:
        for extra in ({"offset": 1, "limit": 2}, {"offset": 0}, {"limit": 0}):
            with self.subTest(extra=extra):
                write_transcript(
                    self.transcript,
                    [
                        read_call(str(self.instructions), "t1", **extra),
                        read_result("t1", RULES),
                    ],
                )
                self.assertTrue(self.denied(self.hook_input()))

    def test_denies_when_the_result_belongs_to_another_call(self) -> None:
        # A qualifying Read exists, but the matching content came from a different call.
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_call(str(self.repo / "copy.md"), "t2"),
                read_result("t2", RULES),
            ],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_denies_after_any_edit_to_the_instructions(self) -> None:
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input()))
        for label, changed in (
            ("added content", RULES + "\nA new binding rule.\n"),
            ("trailing space", RULES.replace("Never commit.", "Never commit. ")),
            ("leading blank", "\n" + RULES),
            ("dropped final newline", RULES.rstrip("\n")),
        ):
            with self.subTest(change=label):
                self.instructions.write_text(changed, encoding="utf-8", newline="")
                self.assertTrue(self.denied(self.hook_input()))
        self.instructions.write_text(RULES, encoding="utf-8")
        self.assertFalse(self.denied(self.hook_input()))

    def test_staleness_is_measured_in_context_tokens(self) -> None:
        write_transcript(
            self.transcript,
            [
                usage_record(100_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                usage_record(260_000),
            ],
        )
        # 160k of context growth since the read.
        self.assertFalse(self.denied(self.hook_input(), max_growth=200_000))
        self.assertTrue(self.denied(self.hook_input(), max_growth=100_000))

    def test_transcript_bulk_alone_does_not_expire_a_read(self) -> None:
        # Large tool output inflates the transcript without occupying much context; the
        # read must survive it.
        bulky = {"type": "user", "toolUseResult": {"content": "x" * 200_000},
                 "message": {"role": "user", "content": []}}
        write_transcript(
            self.transcript,
            [
                usage_record(100_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                bulky,
                usage_record(105_000),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_compaction_after_the_read_makes_it_stale_at_once(self) -> None:
        write_transcript(
            self.transcript,
            [
                usage_record(100_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                compaction_record(),
                usage_record(101_000),
            ],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_a_shrinking_context_counts_as_compaction(self) -> None:
        write_transcript(
            self.transcript,
            [
                usage_record(300_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                usage_record(40_000),
            ],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_a_read_without_usage_data_is_taken_at_face_value(self) -> None:
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input(), max_growth=1))

    def test_a_dip_after_the_read_is_stale_even_if_the_context_recovers(self) -> None:
        write_transcript(
            self.transcript,
            [
                usage_record(100_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                usage_record(300_000),
                usage_record(150_000),
            ],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_a_read_survives_bulky_transcript_output(self) -> None:
        # Transcript size never expires a read; only context growth and compaction do.
        bulky = {"type": "user", "toolUseResult": {"content": "x" * 3_000_000},
                 "message": {"role": "user", "content": []}}
        write_transcript(
            self.transcript,
            [
                usage_record(100_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                bulky,
                usage_record(105_000),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_an_unread_session_is_gated_however_large_the_transcript(self) -> None:
        bulky = {"type": "user", "toolUseResult": {"content": "x" * 3_000_000},
                 "message": {"role": "user", "content": []}}
        write_transcript(self.transcript, [usage_record(100_000), bulky, usage_record(105_000)])
        self.assertTrue(self.denied(self.hook_input()))

    def test_a_content_free_read_result_fails_open(self) -> None:
        # A result that carries no rendered lines cannot be turned into proof by
        # re-reading, so denying would livelock.
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                {"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "t1",
                     "content": "<file unchanged since last read>"}]}},
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_an_unidentifiable_write_target_fails_open(self) -> None:
        write_transcript(self.transcript, [])
        self.assertFalse(self.denied(self.hook_input(tool_input={})))
        self.assertFalse(self.denied(self.hook_input(tool_input="not-a-dict")))

    def test_instructions_past_the_read_line_limit_fail_open(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(self.denied(self.hook_input()))
        # 2000 newline-terminated lines render 2001 numbered lines, past Read's limit.
        self.instructions.write_text("line\n" * 2000, encoding="utf-8")
        self.assertFalse(self.denied(self.hook_input()))

    def test_a_non_utf8_transcript_fails_open(self) -> None:
        self.transcript.write_bytes(b'{"type":"user"}\n\xff\xfe not utf8\n')
        self.assertFalse(self.denied(self.hook_input()))

    def test_denies_on_a_readable_transcript_with_no_records(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(self.denied(self.hook_input()))

    # -- agent isolation --------------------------------------------------------

    def test_subagent_reads_are_judged_against_its_own_transcript(self) -> None:
        write_transcript(
            self.transcript,
            [read_call(str(self.instructions), "t1"), read_result("t1", RULES)],
        )
        agent_dir = self.transcript.parent / self.transcript.stem / "subagents"
        agent_dir.mkdir(parents=True)
        child = agent_dir / "agent-abc123.jsonl"

        write_transcript(
            child, [read_call(str(self.target), "t9"), read_result("t9", "x = 1\n")]
        )
        self.assertTrue(self.denied(self.hook_input(agent_id="abc123")))

        write_transcript(
            child, [read_call(str(self.instructions), "t9"), read_result("t9", RULES)]
        )
        self.assertFalse(self.denied(self.hook_input(agent_id="abc123")))

    def test_a_missing_child_transcript_never_consults_the_parent(self) -> None:
        # The parent has read the file and the child's transcript does not exist: fail
        # open rather than let the parent's read count for the child.
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input(agent_id="missing")))
        # Parent without a read: still fail open, never a livelock.
        write_transcript(
            self.transcript,
            [read_call(str(self.target), "t1"), read_result("t1", "x = 1\n")],
        )
        self.assertFalse(self.denied(self.hook_input(agent_id="missing")))

    # -- repository resolution --------------------------------------------------

    def test_the_target_file_selects_the_repository_not_the_cwd(self) -> None:
        write_transcript(self.transcript, [])
        # Writing into the gated repo from an unrelated cwd is still gated.
        self.assertTrue(self.denied(self.hook_input(cwd="/tmp")))
        # Writing outside any gated repo is not.
        outside = Path(self.tmp.name) / "elsewhere"
        outside.mkdir()
        self.assertFalse(
            self.denied(self.hook_input(tool_input={"file_path": str(outside / "note.md")}))
        )

    def test_relative_target_paths_resolve_against_cwd(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(self.denied(self.hook_input(tool_input={"file_path": "sample.py"})))

    def test_notebook_paths_are_gated_too(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(
            self.denied(
                self.hook_input(
                    tool_name="NotebookEdit",
                    tool_input={"notebook_path": str(self.repo / "nb.ipynb")},
                )
            )
        )

    # -- fail-open paths --------------------------------------------------------

    def test_fails_open_without_usable_inputs_or_instructions(self) -> None:
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input(tool_name="Read")))
        self.assertFalse(self.denied(self.hook_input(transcript_path="/nonexistent/x.jsonl")))
        self.instructions.unlink()
        self.assertFalse(self.denied(self.hook_input()))
        self.instructions.write_text("   \n", encoding="utf-8")
        self.assertFalse(self.denied(self.hook_input()))

    def test_fails_open_for_instructions_too_large_to_read_whole(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(self.denied(self.hook_input()))
        self.instructions.write_text("line\n" * 2500, encoding="utf-8")
        # An unranged Read would be paginated, so the gate could never be satisfied.
        self.assertFalse(self.denied(self.hook_input()))

    def test_fails_open_for_non_utf8_instructions(self) -> None:
        write_transcript(self.transcript, [])
        self.instructions.write_bytes(b"# rules\n\xff\xfe binary\n")
        self.assertFalse(self.denied(self.hook_input()))

    def test_kill_switch_only_honours_an_explicit_one(self) -> None:
        write_transcript(self.transcript, [])
        self.assertTrue(self.denied(self.hook_input()))
        with patch.dict(os.environ, {DISABLE_ENV: "1"}, clear=False):
            self.assertFalse(self.denied(self.hook_input()))
        for value in ("0", "false", "", "yes"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {DISABLE_ENV: value}, clear=False):
                    self.assertTrue(self.denied(self.hook_input()))

    def test_the_first_read_after_compaction_counts(self) -> None:
        # Explicit compact-summary record, then a read.
        write_transcript(
            self.transcript,
            [
                usage_record(300_000),
                compaction_record(),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                usage_record(40_000),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_the_first_read_after_an_implicit_compaction_counts(self) -> None:
        # The context dip is first observed on the record that carries the read itself.
        dipped = read_call(str(self.instructions), "t1")
        dipped["message"]["usage"] = {"input_tokens": 1, "cache_read_input_tokens": 39_999}
        write_transcript(
            self.transcript,
            [usage_record(300_000), dipped, read_result("t1", RULES), usage_record(45_000)],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_a_truncated_read_result_fails_open(self) -> None:
        # Read paginates past its caps; such a result can never match, so denying would
        # livelock the agent.
        record = read_result("t1", RULES)
        record["toolUseResult"] = {"file": {"content": "1\t# AGENTS.md",
                                            "truncatedByTokenCap": True}}
        write_transcript(
            self.transcript, [read_call(str(self.instructions), "t1"), record]
        )
        self.instructions.write_text(RULES + "more\n", encoding="utf-8")
        self.assertFalse(self.denied(self.hook_input()))

    def test_a_file_at_the_render_limit_is_still_gated(self) -> None:
        write_transcript(self.transcript, [])
        # 1999 lines + trailing newline renders exactly 2000 numbered lines, which Read
        # can return in full, so the gate still applies.
        self.instructions.write_text("line\n" * 1999, encoding="utf-8")
        self.assertTrue(self.denied(self.hook_input()))


class StandingRulesGateTests(GateTests):
    """The standing-rules document is gated on presence of a read alone."""

    def test_an_unread_rules_document_is_gated_even_when_agents_md_is_read(self) -> None:
        document = self.rules_document()
        self.compliant_transcript()
        self.assertTrue(self.denied(self.hook_input()))
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                read_call(str(document), "t2"),
                read_result("t2", "1\t# standing rules"),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_its_content_never_has_to_match(self) -> None:
        # A background refresh rewrites it; that must not re-gate the agent.
        document = self.rules_document()
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                read_call(str(document), "t2"),
                read_result("t2", "1\tstale content"),
            ],
        )
        document.write_text("# standing rules\n- entirely different now\n", encoding="utf-8")
        self.assertFalse(self.denied(self.hook_input()))

    def test_a_partial_read_of_it_counts(self) -> None:
        document = self.rules_document()
        write_transcript(
            self.transcript,
            [
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                read_call(str(document), "t2", offset=1, limit=2),
                read_result("t2", "1\t# standing rules"),
            ],
        )
        self.assertFalse(self.denied(self.hook_input()))

    def test_it_expires_with_the_same_window(self) -> None:
        document = self.rules_document()
        write_transcript(
            self.transcript,
            [
                usage_record(10_000),
                read_call(str(self.instructions), "t1"),
                read_result("t1", RULES),
                read_call(str(document), "t2"),
                read_result("t2", "1\t# standing rules"),
                usage_record(400_000),
            ],
        )
        self.assertTrue(self.denied(self.hook_input()))

    def test_an_absent_rules_document_does_not_gate(self) -> None:
        self.compliant_transcript()
        self.assertFalse(self.denied(self.hook_input()))


class ReadOutputMatchingTests(unittest.TestCase):
    def test_requires_sequential_numbering_and_exact_content(self) -> None:
        text = "alpha\nbeta\n"
        self.assertTrue(read_output_matches("1\talpha\n2\tbeta\n3\t", text))
        self.assertFalse(read_output_matches("1\talpha\n2\tbeta", text))
        self.assertFalse(read_output_matches("2\tbeta\n1\talpha\n3\t", text))
        self.assertFalse(read_output_matches("1\talpha\n2\tbet\n3\t", text))
        self.assertFalse(read_output_matches("", text))

    def test_file_content_that_looks_like_a_line_prefix_is_unambiguous(self) -> None:
        # The file's own lines begin with digits and a tab; sequential numbering keeps
        # the comparison honest.
        text = "7\tseven\n8\teight"
        self.assertTrue(read_output_matches("1\t7\tseven\n2\t8\teight", text))
        self.assertFalse(read_output_matches("7\tseven\n8\teight", text))

    def test_whitespace_is_significant(self) -> None:
        self.assertFalse(read_output_matches("1\talpha ", "alpha"))
        self.assertFalse(read_output_matches("1\t alpha", "alpha"))


if __name__ == "__main__":
    unittest.main()
