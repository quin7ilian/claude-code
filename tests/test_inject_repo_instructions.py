from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from inject_repo_instructions import build_injection, find_repo_root  # noqa: E402
from prime_hindsight import rules_path, write_rules  # noqa: E402
from retain_hindsight import stable_project  # noqa: E402


class RepoInstructionInjectionTests(unittest.TestCase):
    def test_points_at_agents_md_without_inlining_its_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                "# Rules\n\nNever commit.\n\n## Testing\n\nRun the suite.\n", encoding="utf-8"
            )
            nested = root / "src" / "deep"
            nested.mkdir(parents=True)

            injection = build_injection(str(nested))

            self.assertIn(str(root / "AGENTS.md"), injection)
            self.assertIn("binding", injection)
            self.assertIn("Read the file in full", injection)
            # Headings are advertised; the rules themselves are not inlined.
            self.assertIn("# Rules", injection)
            self.assertIn("## Testing", injection)
            self.assertNotIn("Never commit.", injection)
            self.assertNotIn("Run the suite.", injection)

    def test_names_the_rules_document_when_one_has_been_recalled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "org" / "repo"
            root.mkdir(parents=True)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
            cache_dir = Path(temporary_directory) / "primer"

            # Nothing recalled yet: the pointer names AGENTS.md and claims nothing more.
            injection = build_injection(str(root), cache_dir=cache_dir)
            self.assertIn(str(root / "AGENTS.md"), injection)
            self.assertNotIn("standing rules", injection)

            project = stable_project(str(root))
            write_rules(cache_dir, project, "# Rules\n\n- a standing rule\n")
            document = rules_path(cache_dir, project)

            injection = build_injection(str(root), cache_dir=cache_dir)

            self.assertIn(str(document), injection)
            self.assertIn("standing rules", injection)
            self.assertIn("gated", injection)
            # A pointer, not the contents.
            self.assertNotIn("- a standing rule", injection)

    def test_skips_when_absent_empty_or_already_imported_by_claude_md(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".git").mkdir()
            self.assertEqual(build_injection(str(root)), "")

            (root / "AGENTS.md").write_text("   \n", encoding="utf-8")
            self.assertEqual(build_injection(str(root)), "")

            (root / "AGENTS.md").write_text("# Real rules\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text("Preamble\n@AGENTS.md\n", encoding="utf-8")
            self.assertEqual(build_injection(str(root)), "")

            (root / "CLAUDE.md").write_text("Unrelated project notes\n", encoding="utf-8")
            self.assertIn("AGENTS.md", build_injection(str(root)))

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
        self.assertEqual(build_injection("/nonexistent/path/xyz"), "")


if __name__ == "__main__":
    unittest.main()
