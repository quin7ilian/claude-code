from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from inject_repo_instructions import build_injection, find_repo_root  # noqa: E402


class RepoInstructionInjectionTests(unittest.TestCase):
    def test_injects_agents_md_found_at_the_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("# Rules\nNever commit.", encoding="utf-8")
            nested = root / "src" / "deep"
            nested.mkdir(parents=True)

            injection = build_injection(str(nested), 40000)

            self.assertIn("Never commit.", injection)
            self.assertIn("binding", injection)
            self.assertIn(str(root / "AGENTS.md"), injection)
            self.assertIn("<repository-instructions", injection)

    def test_skips_when_absent_empty_or_already_imported_by_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            self.assertEqual(build_injection(str(root), 40000), "")

            (root / "AGENTS.md").write_text("   \n", encoding="utf-8")
            self.assertEqual(build_injection(str(root), 40000), "")

            (root / "AGENTS.md").write_text("Real rules", encoding="utf-8")
            (root / "CLAUDE.md").write_text("Preamble\n@AGENTS.md\n", encoding="utf-8")
            self.assertEqual(build_injection(str(root), 40000), "")

            (root / "CLAUDE.md").write_text("Unrelated project notes\n", encoding="utf-8")
            self.assertIn("Real rules", build_injection(str(root), 40000))

    def test_truncates_oversized_instructions_with_a_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("x" * 500, encoding="utf-8")

            injection = build_injection(str(root), 100)

            self.assertIn("Truncated at 100 characters", injection)
            self.assertLess(len(injection), 900)

    def test_repo_root_prefers_vcs_marker_then_falls_back_to_agents_md(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            inner = root / "sub"
            inner.mkdir()
            (inner / "AGENTS.md").write_text("inner", encoding="utf-8")
            # The VCS marker wins over a nearer AGENTS.md.
            self.assertEqual(find_repo_root(inner), root.resolve())

        # A project with no VCS marker still resolves via its AGENTS.md.
        with tempfile.TemporaryDirectory() as other_directory:
            plain = Path(other_directory) / "plain"
            (plain / "nested").mkdir(parents=True)
            (plain / "AGENTS.md").write_text("rules", encoding="utf-8")
            self.assertEqual(find_repo_root(plain / "nested"), plain.resolve())

    def test_missing_directory_is_safe(self) -> None:
        self.assertEqual(build_injection("/nonexistent/path/xyz", 40000), "")


if __name__ == "__main__":
    unittest.main()
