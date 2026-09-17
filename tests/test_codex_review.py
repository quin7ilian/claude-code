from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


CODEX_REVIEW = Path(__file__).resolve().parents[1] / "bin" / "codex-review"

# Codex writes its banner and diagnostics to stderr and the review to stdout. The stub mirrors
# that split, records the argv it was handed, and fails a resume when FAIL_ON_RESUME is set.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$ARGV_LOG"
printf '%s\\n' "${@: -1}" > "$PROMPT_LOG"
{ echo "OpenAI Codex v0.154.0"; echo "session id: __SESSION_ID__"; } >&2
if [ -n "${FAIL_ON_RESUME:-}" ] && [ "${1:-}" = "exec" ] && [ "${2:-}" = "resume" ]; then
  echo "resume: no such session" >&2
  exit 1
fi
if [ -n "${EMPTY_REVIEW:-}" ]; then
  exit 0
fi
echo "REVIEW BODY"
echo "verdict: PASS"
"""

SESSION_ID = "01a0acb5-9f41-7813-abed-87042eae4309"


class CodexReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        bindir = self.root / "bin"
        bindir.mkdir()
        stub = bindir / "codex"
        stub.write_text(STUB.replace("__SESSION_ID__", SESSION_ID))
        stub.chmod(0o755)

        self.brief = self.root / "brief.md"
        self.brief.write_text("# Brief\n")
        self.prior = self.root / "codex-review--thing--r1.md"
        self.prior.write_text("finding 1: the original words\n")
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.session_file = self.root / "session.id"

        self.env = dict(os.environ)
        self.env["PATH"] = f"{bindir}:{self.env['PATH']}"
        self.env["ARGV_LOG"] = str(self.root / "argv.txt")
        self.env["PROMPT_LOG"] = str(self.root / "prompt.txt")

    def run_review(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(CODEX_REVIEW), "--brief", str(self.brief), "--repo", str(self.repo), *args],
            capture_output=True,
            text=True,
            env=self.env,
        )

    def argv(self) -> list[str]:
        return Path(self.env["ARGV_LOG"]).read_text().splitlines()

    def prompt(self) -> str:
        return Path(self.env["PROMPT_LOG"]).read_text()

    def test_fresh_run_records_the_session_id(self) -> None:
        out = self.root / "review.md"
        result = self.run_review("--out", str(out), "--session-file", str(self.session_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REVIEW BODY", out.read_text())
        self.assertEqual(self.session_file.read_text().strip(), SESSION_ID)
        argv = self.argv()
        self.assertEqual(argv[0], "exec")
        self.assertIn("--sandbox", argv)
        self.assertIn("workspace-write", argv)

    def test_resume_reasserts_the_sandbox_and_names_the_session(self) -> None:
        self.session_file.write_text(f"{SESSION_ID}\n")
        result = self.run_review(
            "--out", str(self.root / "r2.md"),
            "--session-file", str(self.session_file),
            "--resume",
            "--prior", str(self.prior),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.argv()
        self.assertEqual(argv[:3], ["exec", "resume", SESSION_ID])
        # resume takes no --sandbox flag, so the policy has to arrive as a config override or
        # the run falls back to the user's configured default.
        self.assertIn('sandbox_mode="workspace-write"', argv)
        self.assertNotIn("--sandbox", argv)

    def test_every_prior_round_is_named_in_the_prompt(self) -> None:
        second = self.root / "codex-review--thing--r2.md"
        second.write_text("finding 2\n")
        self.session_file.write_text(f"{SESSION_ID}\n")
        result = self.run_review(
            "--session-file", str(self.session_file),
            "--resume",
            "--prior", str(self.prior),
            "--prior", str(second),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = self.prompt()
        self.assertIn(str(self.prior), prompt)
        self.assertIn(str(second), prompt)
        self.assertIn("stale", prompt)

    def test_failed_resume_falls_back_to_a_fresh_session(self) -> None:
        self.session_file.write_text(f"{SESSION_ID}\n")
        self.env["FAIL_ON_RESUME"] = "1"
        out = self.root / "r3.md"
        result = self.run_review(
            "--out", str(out),
            "--session-file", str(self.session_file),
            "--resume",
            "--prior", str(self.prior),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REVIEW BODY", out.read_text())
        self.assertIn("could not resume", result.stderr)
        self.assertEqual(self.argv()[0], "exec")
        self.assertNotIn("resume", self.argv()[:2])
        # The fallback's own prompt still carries the prior round.
        self.assertIn(str(self.prior), self.prompt())

    def test_empty_review_is_never_a_pass(self) -> None:
        self.env["EMPTY_REVIEW"] = "1"
        result = self.run_review("--out", str(self.root / "r4.md"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("NOT a pass", result.stderr)

    def test_resume_requires_a_session_file_and_a_prior(self) -> None:
        missing_prior = self.run_review("--session-file", str(self.session_file), "--resume")
        self.assertEqual(missing_prior.returncode, 2)
        self.assertIn("--prior", missing_prior.stderr)

        missing_session = self.run_review("--resume", "--prior", str(self.prior))
        self.assertEqual(missing_session.returncode, 2)
        self.assertIn("--session-file", missing_session.stderr)

    def test_unreadable_prior_stops_the_run(self) -> None:
        result = self.run_review("--prior", str(self.root / "gone.md"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("prior review not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
