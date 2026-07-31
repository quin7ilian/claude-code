from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from retain_hindsight import RetentionConfig, RetentionError  # noqa: E402
import prime_hindsight  # noqa: E402
from prime_hindsight import (  # noqa: E402
    build_primer,
    collect_sections,
    read_cache,
    render_rules,
    rules_path,
    same_project,
    write_cache,
    write_rules,
)


CONFIG = RetentionConfig(
    api_base_url="https://hindsight.example",
    bank_id="main",
    headers={"Authorization": "Bearer x", "X-Bank-Id": "main"},
)


class FakeTransport:
    def __init__(
        self,
        directives: dict | BaseException,
        recalls: list[dict | BaseException],
    ) -> None:
        self.directives = directives
        self.recalls = list(recalls)
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, url, headers, body, timeout):  # noqa: ANN001
        self.calls.append((method, url, body))
        if "directives" in url:
            response = self.directives
        elif "recall" in url:
            if not self.recalls:
                raise AssertionError("no recall response queued")
            response = self.recalls.pop(0)
        else:
            raise AssertionError(f"no fake response for {url}")
        if isinstance(response, BaseException):
            raise response
        return response


class PrimerTests(unittest.TestCase):
    def test_rules_are_directives_only_and_context_is_recalled(self) -> None:
        transport = FakeTransport(
            directives={"items": [{"name": "Never drop git stashes"}]},
            recalls=[
                {
                    "results": [
                        {"text": "User prohibits commits and branches"},
                        {"text": "User  prohibits commits   and branches"},
                        {"text": "User opened the file /x/y.py in the IDE."},
                        {"text": "Project uses catalog-owned warmup"},
                    ]
                },
            ],
        )

        primer = build_primer(CONFIG, "org/repo", 5.0, transport=transport)

        self.assertIn("generated ", primer)
        self.assertIn("## Standing rules and preferences", primer)
        self.assertIn("- Never drop git stashes", primer)
        self.assertIn("## org/repo context", primer)
        self.assertIn("catalog-owned warmup", primer)
        # Whitespace-only variants collapse to one fact.
        self.assertEqual(primer.count("prohibits commits and branches"), 1)
        # What belongs in the primer is decided by the query put to Hindsight, so
        # whatever it returns is rendered as-is rather than pattern-filtered here.
        self.assertIn("User opened the file /x/y.py in the IDE.", primer)
        # Exactly one recall: rules come from directives, never from a rules recall.
        recall_bodies = [c[2] for c in transport.calls if "recall" in c[1]]
        self.assertEqual(len(recall_bodies), 1)
        self.assertEqual(recall_bodies[0]["budget"], "low")
        self.assertIn("query_timestamp", recall_bodies[0])
        self.assertIn("org/repo", recall_bodies[0]["query"])

    def test_sections_fail_open_independently(self) -> None:
        transport = FakeTransport(
            directives=RetentionError("network: down"),
            recalls=[{"results": [{"text": "Fact survives"}]}],
        )
        primer = build_primer(CONFIG, "org/repo", 5.0, transport=transport)
        self.assertIn("Fact survives", primer)
        self.assertNotIn("## Standing rules and preferences", primer)

        directives_only = FakeTransport(
            directives={"items": [{"name": "Never drop git stashes"}]},
            recalls=[RetentionError("network: down")],
        )
        primer = build_primer(CONFIG, "org/repo", 5.0, transport=directives_only)
        self.assertIn("- Never drop git stashes", primer)
        self.assertNotIn("## org/repo context", primer)

        all_down = FakeTransport(
            directives=RetentionError("network: down"),
            recalls=[RetentionError("network: down")],
        )
        self.assertEqual(build_primer(CONFIG, "org/repo", 5.0, transport=all_down), "")

    def test_refresh_budget_is_passed_through_to_recall(self) -> None:
        transport = FakeTransport(
            directives={"items": []},
            recalls=[{"results": [{"text": "a"}]}],
        )
        build_primer(CONFIG, "org/repo", 5.0, budget="high", transport=transport)
        for call in transport.calls:
            if "recall" in call[1]:
                self.assertEqual(call[2]["budget"], "high")

    def test_rules_document_carries_directives_verbatim(self) -> None:
        directives = [
            "Never commit, branch, or stage changes yourself",
            "Verify before asserting or proposing",
        ]
        document = render_rules("org/repo", directives)

        self.assertIn("# Standing rules and preferences (org/repo, recalled ", document)
        self.assertIn("File writes are gated on having read them.", document)
        for rule in directives:
            self.assertIn(f"- {rule}", document)
        self.assertTrue(document.endswith("\n"))
        self.assertEqual(document.count("\n- "), len(directives))
        self.assertEqual(render_rules("org/repo", []), "")


class DirectiveFetchOutcomeTests(unittest.TestCase):
    """A failed fetch and an empty bank must stay distinguishable: the rules document is
    deleted on the second, and deleting it on the first leaves the gate with no rules."""

    def _collect(self, transport):
        return collect_sections(CONFIG, "org/repo", 5.0, "low", transport)

    def test_failure_reports_none_and_empty_bank_reports_empty_list(self) -> None:
        failed = FakeTransport(
            directives=RetentionError("network: down"),
            recalls=[{"results": [{"text": "Context fact"}]}],
        )
        directives, context = self._collect(failed)
        self.assertIsNone(directives)
        self.assertEqual(context, ["Context fact"])

        empty = FakeTransport(
            directives={"items": []},
            recalls=[{"results": [{"text": "Context fact"}]}],
        )
        directives, context = self._collect(empty)
        self.assertEqual(directives, [])

    def test_malformed_directives_fail_without_suppressing_context(self) -> None:
        malformed = (
            {},
            {"items": None},
            {"items": "nope"},
            {"items": {"a": 1}},
            # A shrinking set is the dangerous case: skipping unreadable entries would
            # reduce these to [], which reads as a bank holding no directives at all.
            {"items": [None]},
            {"items": [{"name": None}]},
            {"items": [{"name": "  "}]},
            {"items": [{"title": "renamed field"}]},
            {"items": [{"name": "A real rule"}, {"name": None}]},
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                transport = FakeTransport(
                    directives=payload,
                    recalls=[{"results": [{"text": "Context survives"}]}],
                )
                directives, context = self._collect(transport)
                self.assertIsNone(directives)
                self.assertEqual(context, ["Context survives"])

    def test_malformed_recall_fails_without_suppressing_directives(self) -> None:
        for payload in ({}, {"results": None}, {"results": "nope"}):
            with self.subTest(payload=payload):
                transport = FakeTransport(
                    directives={"items": [{"name": "A real rule"}]},
                    recalls=[payload],
                )
                directives, context = self._collect(transport)
                self.assertEqual(directives, ["A real rule"])
                self.assertEqual(context, [])

    def test_directive_names_are_collapsed_but_never_truncated(self) -> None:
        long_rule = "Never " + "x" * 600
        wrapped = "Rule with\n  wrapped   text"
        transport = FakeTransport(
            directives={"items": [{"name": long_rule}, {"name": wrapped}]},
            recalls=[{"results": []}],
        )
        directives, _ = self._collect(transport)

        self.assertEqual(directives[0], long_rule)
        self.assertNotIn("…", directives[0])
        self.assertEqual(directives[1], "Rule with wrapped text")
        # End to end: the gated document carries the whole rule, not a clipped one.
        self.assertIn(long_rule, render_rules("org/repo", directives))


class RulesDocumentCleanupTests(unittest.TestCase):
    def _refresh(self, transport, cache_dir: Path) -> None:
        args = argparse.Namespace(
            cwd=Path("/repo"),
            cache_dir=cache_dir,
            env_file=Path("/nonexistent"),
            http_timeout=5.0,
            refresh=True,
        )
        with (
            mock.patch.object(prime_hindsight, "load_retention_config", return_value=CONFIG),
            mock.patch.object(prime_hindsight, "default_transport", transport),
            mock.patch.object(prime_hindsight, "project_identity", return_value="org/repo"),
        ):
            prime_hindsight.run_refresh(args)

    def test_failed_directive_fetch_keeps_the_existing_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            write_rules(cache_dir, "org/repo", "# EXISTING\n- a real rule\n")
            document = rules_path(cache_dir, "org/repo")

            self._refresh(
                FakeTransport(
                    directives=RetentionError("network: down"),
                    recalls=[{"results": [{"text": "Context fact"}]}],
                ),
                cache_dir,
            )

            self.assertTrue(document.exists())
            self.assertIn("a real rule", document.read_text(encoding="utf-8"))

    def test_empty_bank_removes_the_obsolete_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            write_rules(cache_dir, "org/repo", "# STALE\n- a withdrawn rule\n")
            document = rules_path(cache_dir, "org/repo")

            self._refresh(
                FakeTransport(
                    directives={"items": []},
                    recalls=[{"results": [{"text": "Context fact"}]}],
                ),
                cache_dir,
            )

            self.assertFalse(document.exists())

    def _cache_miss(self, transport, cache_dir: Path) -> str:
        """Drive `main()` down the SessionStart cache-miss path."""
        args = argparse.Namespace(
            cwd=None,
            cache_dir=cache_dir,
            env_file=Path("/nonexistent"),
            http_timeout=5.0,
            refresh=False,
        )
        hook_input = json.dumps({"hook_event_name": "SessionStart", "cwd": "/repo"})
        printed: list[str] = []
        with (
            mock.patch.object(prime_hindsight, "parse_args", return_value=args),
            mock.patch.object(prime_hindsight, "load_retention_config", return_value=CONFIG),
            mock.patch.object(prime_hindsight, "default_transport", transport),
            mock.patch.object(prime_hindsight, "project_identity", return_value="org/repo"),
            mock.patch.object(prime_hindsight, "kick_refresh", lambda *a: None),
            mock.patch("sys.stdin", io.StringIO(hook_input)),
            mock.patch("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a)))),
        ):
            self.assertEqual(prime_hindsight.main(), 0)
        return "\n".join(printed)

    def test_cache_miss_retires_the_document_even_with_an_empty_primer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            write_rules(cache_dir, "org/repo", "# STALE\n- a withdrawn rule\n")
            document = rules_path(cache_dir, "org/repo")

            # Empty bank and empty context: the primer is empty, but the document is still
            # obsolete and must not survive on the strength of that.
            output = self._cache_miss(
                FakeTransport(directives={"items": []}, recalls=[{"results": []}]),
                cache_dir,
            )

            self.assertEqual(output, "")
            self.assertFalse(document.exists())

    def test_cache_miss_keeps_the_document_when_the_fetch_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            write_rules(cache_dir, "org/repo", "# EXISTING\n- a real rule\n")
            document = rules_path(cache_dir, "org/repo")

            self._cache_miss(
                FakeTransport(
                    directives=RetentionError("network: down"),
                    recalls=[RetentionError("network: down")],
                ),
                cache_dir,
            )

            self.assertTrue(document.exists())
            self.assertIn("a real rule", document.read_text(encoding="utf-8"))

    def test_directives_are_written_to_the_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"

            self._refresh(
                FakeTransport(
                    directives={"items": [{"name": "Never commit on the user's behalf"}]},
                    recalls=[{"results": [{"text": "Context fact"}]}],
                ),
                cache_dir,
            )

            document = rules_path(cache_dir, "org/repo")
            self.assertTrue(document.exists())
            body = document.read_text(encoding="utf-8")
            self.assertIn("- Never commit on the user's behalf", body)
            self.assertNotIn("Context fact", body)
            self.assertEqual(document.stat().st_mode & 0o777, 0o600)


class ProjectScopingTests(unittest.TestCase):
    def test_legacy_path_shaped_project_names_match_stable_identity(self) -> None:
        wanted = "swing-traders/nautilus-trader"
        for legacy in (
            "swing-traders/nautilus-trader",
            "-var-home-user-Work-src-swing-traders-nautilus-trader",
            "-home-user-Work-src-swing-traders-nautilus-trader",
            "D--Work-src-swing-traders-nautilus-trader",
        ):
            self.assertTrue(same_project(legacy, wanted), legacy)
        for other in ("quin7ilian/claude-code", "swing-traders/jesse", "", "nautilus"):
            self.assertFalse(same_project(other, wanted), other)

    def test_context_section_drops_other_projects_but_keeps_unattributed(self) -> None:
        transport = FakeTransport(
            directives={"items": []},
            recalls=[
                {
                    "results": [
                        {
                            "text": "Nautilus current state",
                            "metadata": {"project": "swing-traders/nautilus-trader"},
                        },
                        {
                            "text": "Legacy nautilus fact",
                            "metadata": {
                                "project": "-var-home-user-Work-src-swing-traders-nautilus-trader"
                            },
                        },
                        {
                            "text": "Unrelated claude-code work",
                            "metadata": {"project": "quin7ilian/claude-code"},
                        },
                        {"text": "Unattributed legacy fact", "metadata": {}},
                    ]
                },
            ],
        )

        primer = build_primer(
            CONFIG, "swing-traders/nautilus-trader", 5.0, transport=transport
        )

        self.assertIn("Nautilus current state", primer)
        self.assertIn("Legacy nautilus fact", primer)
        self.assertIn("Unattributed legacy fact", primer)
        self.assertNotIn("Unrelated claude-code work", primer)


class CacheTests(unittest.TestCase):
    def test_roundtrip_is_user_only_and_survives_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            self.assertIsNone(read_cache(cache_dir, "org/repo"))

            write_cache(cache_dir, "org/repo", "PRIMER BODY")

            self.assertEqual(read_cache(cache_dir, "org/repo"), "PRIMER BODY")
            self.assertIsNone(read_cache(cache_dir, "other/repo"))
            self.assertEqual(cache_dir.stat().st_mode & 0o777, 0o700)
            cache_file = next(cache_dir.glob("*.json"))
            self.assertEqual(cache_file.stat().st_mode & 0o777, 0o600)

    def test_corrupt_or_versioned_out_cache_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_dir = Path(temporary_directory) / "primer"
            write_cache(cache_dir, "org/repo", "PRIMER BODY")
            cache_file = next(cache_dir.glob("*.json"))

            cache_file.write_text("not json", encoding="utf-8")
            self.assertIsNone(read_cache(cache_dir, "org/repo"))

            cache_file.write_text(
                json.dumps({"version": 999, "primer": "stale format"}), encoding="utf-8"
            )
            self.assertIsNone(read_cache(cache_dir, "org/repo"))

            cache_file.write_text(json.dumps({"version": 1, "primer": ""}), encoding="utf-8")
            self.assertIsNone(read_cache(cache_dir, "org/repo"))


if __name__ == "__main__":
    unittest.main()
