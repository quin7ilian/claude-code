from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from configure_settings import (  # noqa: E402
    hook_command,
    load_settings,
    merge_settings,
    primer_command,
    write_settings,
)


SCRIPT = Path("/home/user/.claude/hooks/retain_hindsight.py")
PRIMER = Path("/home/user/.claude/hooks/prime_hindsight.py")
INSTRUCTIONS = Path("/home/user/.claude/hooks/inject_repo_instructions.py")
INSTRUCTIONS_CMD = f"/usr/bin/python3 {INSTRUCTIONS}"
GATE = Path("/home/user/.claude/hooks/gate_repo_instructions.py")
GATE_CMD = f"/usr/bin/python3 {GATE}"


def owned_command() -> str:
    return hook_command(
        Path("/usr/bin/python3"),
        SCRIPT,
        Path("/home/user/.claude/.env"),
        Path("/home/user/.claude/hindsight-retention"),
    )


def owned_primer_command() -> str:
    return primer_command(
        Path("/usr/bin/python3"), PRIMER, Path("/home/user/.claude/.env")
    )


class SettingsConfigTests(unittest.TestCase):
    def test_merge_preserves_foreign_hooks_and_replaces_owned_handler(self) -> None:
        foreign_handler = {
            "type": "command",
            "command": "python3 /tmp/foreign.py",
            "timeout": 10,
        }
        document = {
            "model": "fable",
            "permissions": {"allow": ["Bash(ls:*)"]},
            "hooks": {
                "SessionStart": [{"hooks": [foreign_handler]}],
                "Stop": [
                    {"matcher": "*", "hooks": [foreign_handler]},
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"python3 {SCRIPT} --old-flag",
                            }
                        ],
                    },
                ],
            },
        }

        merged = merge_settings(document, owned_command(), SCRIPT)

        self.assertEqual(merged["model"], "fable")
        self.assertEqual(merged["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertEqual(merged["hooks"]["SessionStart"], [{"hooks": [foreign_handler]}])
        stop_handlers = [
            handler
            for group in merged["hooks"]["Stop"]
            for handler in group.get("hooks", [])
        ]
        self.assertIn(foreign_handler, stop_handlers)
        for event in ("Stop", "SessionEnd"):
            owned = [
                handler
                for group in merged["hooks"][event]
                for handler in group.get("hooks", [])
                if handler.get("command") == owned_command()
            ]
            self.assertEqual(len(owned), 1)
            self.assertEqual(owned[0]["timeout"], 10)

    def test_merge_removes_legacy_curator_handlers_from_all_events(self) -> None:
        document = {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/home/user/.local/bin/cc-retain",
                                "async": True,
                            }
                        ],
                    }
                ],
                "SessionEnd": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/home/user/.local/bin/cc-retain --force",
                            }
                        ]
                    }
                ],
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/home/user/.local/bin/cc-reconcile-nudge",
                            },
                            {"type": "command", "command": "python3 /tmp/keep.py"},
                        ]
                    }
                ],
            }
        }

        merged = merge_settings(document, owned_command(), SCRIPT)

        session_start_commands = [
            handler.get("command")
            for group in merged["hooks"]["SessionStart"]
            for handler in group.get("hooks", [])
        ]
        self.assertEqual(session_start_commands, ["python3 /tmp/keep.py"])
        for event in ("Stop", "SessionEnd"):
            commands = [
                handler.get("command")
                for group in merged["hooks"][event]
                for handler in group.get("hooks", [])
            ]
            self.assertEqual(commands, [owned_command()])

    def test_env_default_is_added_only_when_absent(self) -> None:
        fresh = merge_settings({}, owned_command(), SCRIPT)
        self.assertEqual(fresh["env"]["MAX_MCP_OUTPUT_TOKENS"], "50000")

        tuned = merge_settings(
            {"env": {"MAX_MCP_OUTPUT_TOKENS": "90000"}}, owned_command(), SCRIPT
        )
        self.assertEqual(tuned["env"]["MAX_MCP_OUTPUT_TOKENS"], "90000")

    def test_auto_memory_is_forced_off(self) -> None:
        fresh = merge_settings({}, owned_command(), SCRIPT)
        self.assertIs(fresh["autoMemoryEnabled"], False)

        toggled = merge_settings({"autoMemoryEnabled": True}, owned_command(), SCRIPT)
        self.assertIs(toggled["autoMemoryEnabled"], False)

    def test_primer_is_registered_on_session_start_alongside_foreign_hooks(self) -> None:
        foreign_handler = {"type": "command", "command": "python3 /tmp/keep.py"}
        document = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [foreign_handler]},
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/home/user/.local/bin/cc-reconcile-nudge",
                            }
                        ]
                    },
                ]
            }
        }

        merged = merge_settings(
            document,
            owned_command(),
            SCRIPT,
            owned_primer_command(),
            PRIMER,
            INSTRUCTIONS_CMD,
            INSTRUCTIONS,
            GATE_CMD,
            GATE,
        )

        session_start = [
            handler.get("command")
            for group in merged["hooks"]["SessionStart"]
            for handler in group.get("hooks", [])
        ]
        self.assertEqual(
            session_start,
            ["python3 /tmp/keep.py", owned_primer_command(), INSTRUCTIONS_CMD],
        )

        # SessionEnd carries both owned scripts: retention, then the cache refresh.
        session_end = [
            handler.get("command")
            for group in merged["hooks"]["SessionEnd"]
            for handler in group.get("hooks", [])
        ]
        self.assertEqual(session_end, [owned_command(), owned_primer_command()])

        # The write gate is registered on PreToolUse for the writing tools.
        gate_groups = merged["hooks"]["PreToolUse"]
        self.assertEqual(len(gate_groups), 1)
        self.assertEqual(gate_groups[0]["matcher"], "Edit|Write|MultiEdit|NotebookEdit")
        self.assertEqual(
            [h.get("command") for h in gate_groups[0]["hooks"]], [GATE_CMD]
        )

    def test_merge_is_idempotent(self) -> None:
        def merge(document: dict) -> str:
            merge_settings(
                document,
                owned_command(),
                SCRIPT,
                owned_primer_command(),
                PRIMER,
                INSTRUCTIONS_CMD,
                INSTRUCTIONS,
                GATE_CMD,
                GATE,
            )
            return json.dumps(document, sort_keys=True)

        document: dict = {}
        first = merge(document)
        self.assertEqual(merge(document), first)

    def test_unreadable_or_non_object_settings_files_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            settings_path.write_text("not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings(settings_path)
            settings_path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings(settings_path)

    def test_write_is_byte_stable_and_user_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_path = Path(temporary_directory) / "settings.json"
            document = {"hooks": {"Stop": []}}

            write_settings(settings_path, document)
            first = settings_path.read_bytes()
            first_mtime = settings_path.stat().st_mtime_ns
            write_settings(settings_path, document)

            self.assertEqual(settings_path.read_bytes(), first)
            self.assertEqual(settings_path.stat().st_mtime_ns, first_mtime)
            self.assertEqual(settings_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
