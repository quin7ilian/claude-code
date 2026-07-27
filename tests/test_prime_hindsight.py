from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from retain_hindsight import RetentionConfig, RetentionError  # noqa: E402
from prime_hindsight import (  # noqa: E402
    build_primer,
    read_cache,
    same_project,
    write_cache,
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
    def test_sections_rules_first_with_noise_filtered_and_deduped(self) -> None:
        transport = FakeTransport(
            directives={"items": [{"name": "Never drop git stashes"}]},
            recalls=[
                {
                    "results": [
                        {"text": "User prohibits commits and branches"},
                        {"text": "User opened the file /x/y.py in the IDE."},
                        {"text": "Note recorded in project X, migrated into Hindsight"},
                        {"text": "A curated memory note was created on Thursday"},
                        {"text": "Reflect Mission is visible at Bank configuration"},
                    ]
                },
                {
                    "results": [
                        {"text": "User  prohibits commits   and branches"},
                        {"text": "The project is org/repo."},
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
        self.assertEqual(primer.count("prohibits commits and branches"), 1)
        self.assertIn("catalog-owned warmup", primer)
        self.assertNotIn("IDE", primer)
        self.assertNotIn("migrated", primer)
        self.assertNotIn("curated memory note", primer)
        self.assertNotIn("Reflect Mission", primer)
        self.assertNotIn("The project is org/repo.", primer)
        # both recall calls use low budget and a query timestamp
        recall_bodies = [c[2] for c in transport.calls if "recall" in c[1]]
        self.assertEqual(len(recall_bodies), 2)
        for body in recall_bodies:
            self.assertEqual(body["budget"], "low")
            self.assertIn("query_timestamp", body)
        self.assertIn("org/repo", recall_bodies[1]["query"])

    def test_sections_fail_open_independently(self) -> None:
        transport = FakeTransport(
            directives=RetentionError("network: down"),
            recalls=[
                RetentionError("network: down"),
                {"results": [{"text": "Fact survives"}]},
            ],
        )
        primer = build_primer(CONFIG, "org/repo", 5.0, transport=transport)
        self.assertIn("Fact survives", primer)

        all_down = FakeTransport(
            directives=RetentionError("network: down"),
            recalls=[RetentionError("network: down"), RetentionError("network: down")],
        )
        self.assertEqual(build_primer(CONFIG, "org/repo", 5.0, transport=all_down), "")

    def test_refresh_budget_is_passed_through_to_recall(self) -> None:
        transport = FakeTransport(
            directives={"items": []},
            recalls=[{"results": [{"text": "a"}]}, {"results": [{"text": "b"}]}],
        )
        build_primer(CONFIG, "org/repo", 5.0, budget="high", transport=transport)
        for call in transport.calls:
            if "recall" in call[1]:
                self.assertEqual(call[2]["budget"], "high")


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
                {"results": [{"text": "Global preference: never commit"}]},
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
        # Rules stay unscoped: a preference from any project still applies.
        self.assertIn("Global preference: never commit", primer)


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
