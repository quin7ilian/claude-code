#!/usr/bin/env python3
"""Merge the repository-owned session hooks into Claude Code settings.json.

Manages the retention script under hooks.Stop and hooks.SessionEnd, the memory primer
under hooks.SessionStart and hooks.SessionEnd, the instruction announcement under
hooks.SessionStart, and the write gate under hooks.PreToolUse — plus the
MAX_MCP_OUTPUT_TOKENS env default and the auto-memory switch.

Everything else in the settings file — foreign hooks, unknown keys, user tuning — is
preserved byte-for-byte. Handlers left behind by retired tooling (cc-retain,
cc-reconcile-nudge) are removed from every hook event they appear under. Idempotent:
re-running with the same inputs leaves the file untouched.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from typing import Any


MAX_MCP_OUTPUT_TOKENS = "50000"
LEGACY_COMMAND_BASENAMES = ("cc-retain", "cc-reconcile-nudge")
LEGACY_EVENTS = ("Stop", "SessionEnd", "SessionStart")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--primer-script", required=True, type=Path)
    parser.add_argument("--instructions-script", required=True, type=Path)
    parser.add_argument("--gate-script", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    return parser.parse_args()


def primer_command(python_path: Path, primer_script: Path, env_path: Path) -> str:
    arguments = (
        str(python_path),
        str(primer_script),
        "--env-file",
        str(env_path),
    )
    return " ".join(shlex.quote(argument) for argument in arguments)


def hook_command(
    python_path: Path,
    script_path: Path,
    env_path: Path,
    state_dir: Path,
) -> str:
    arguments = (
        str(python_path),
        str(script_path),
        "--env-file",
        str(env_path),
        "--state-dir",
        str(state_dir),
        "--http-timeout",
        "3.0",
    )
    return " ".join(shlex.quote(argument) for argument in arguments)


def _command_arguments(handler: Any) -> list[str]:
    if not isinstance(handler, dict) or handler.get("type") != "command":
        return []
    command = handler.get("command")
    if not isinstance(command, str):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _handler_uses_script(handler: Any, script_path: Path) -> bool:
    return str(script_path) in _command_arguments(handler)


def _handler_is_legacy(handler: Any) -> bool:
    return any(
        os.path.basename(argument) in LEGACY_COMMAND_BASENAMES
        for argument in _command_arguments(handler)
    )


def _without_handlers(groups: list[Any], drop: Any) -> list[Any]:
    """Return the hook groups with handlers matching `drop` removed; groups whose handlers
    all matched are dropped entirely, everything unrecognized passes through unchanged."""
    retained_groups: list[Any] = []
    for group in groups:
        if not isinstance(group, dict):
            retained_groups.append(group)
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            retained_groups.append(group)
            continue
        retained_handlers = [handler for handler in handlers if not drop(handler)]
        if retained_handlers:
            updated_group = dict(group)
            updated_group["hooks"] = retained_handlers
            retained_groups.append(updated_group)
    return retained_groups


def _ensure_owned_entry(
    hooks: dict[str, Any], event: str, command: str, script_path: Path, timeout: int
) -> None:
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        raise ValueError(f"settings.json field 'hooks.{event}' must be an array")
    retained_groups = _without_handlers(
        groups, lambda handler: _handler_uses_script(handler, script_path)
    )
    retained_groups.append(
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": timeout,
                }
            ],
        }
    )
    hooks[event] = retained_groups


def merge_settings(
    document: dict[str, Any],
    command: str,
    script_path: Path,
    primer_cmd: str | None = None,
    primer_script: Path | None = None,
    instructions_cmd: str | None = None,
    instructions_script: Path | None = None,
    gate_cmd: str | None = None,
    gate_script: Path | None = None,
) -> dict[str, Any]:
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings.json field 'hooks' must be an object")

    for event in LEGACY_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        remaining = _without_handlers(groups, _handler_is_legacy)
        if remaining:
            hooks[event] = remaining
        else:
            del hooks[event]

    # The retention script runs on Stop (every completed turn) and SessionEnd (the final
    # chance to resubmit a turn whose transcript tail was not yet flushed at its Stop).
    for event in ("Stop", "SessionEnd"):
        _ensure_owned_entry(hooks, event, command, script_path, timeout=10)

    # The memory primer serves a cached project brief into the session's opening context
    # on SessionStart (so baseline memory never depends on the model choosing to recall),
    # and spawns a detached cache refresh on both events — on SessionStart so the next
    # session sees fresher memory, on SessionEnd so the cache reflects the session that
    # just finished.
    if primer_cmd is not None and primer_script is not None:
        _ensure_owned_entry(hooks, "SessionStart", primer_cmd, primer_script, timeout=15)
        _ensure_owned_entry(hooks, "SessionEnd", primer_cmd, primer_script, timeout=5)

    # Claude Code auto-loads CLAUDE.md but not AGENTS.md, so this hook announces the
    # repository's AGENTS.md at session start: path, headings, and notice of the gate.
    if instructions_cmd is not None and instructions_script is not None:
        _ensure_owned_entry(
            hooks, "SessionStart", instructions_cmd, instructions_script, timeout=5
        )

    # Writes are gated on having read the repository's AGENTS.md. This fires for subagent
    # tool calls as well as the main session.
    if gate_cmd is not None and gate_script is not None:
        groups = hooks.setdefault("PreToolUse", [])
        if not isinstance(groups, list):
            raise ValueError("settings.json field 'hooks.PreToolUse' must be an array")
        retained = _without_handlers(
            groups, lambda handler: _handler_uses_script(handler, gate_script)
        )
        retained.append(
            {
                "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                "hooks": [{"type": "command", "command": gate_cmd, "timeout": 10}],
            }
        )
        hooks["PreToolUse"] = retained

    env = document.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError("settings.json field 'env' must be an object")
    # Never clobber a user-tuned value; only supply the default when the key is absent.
    env.setdefault("MAX_MCP_OUTPUT_TOKENS", MAX_MCP_OUTPUT_TOKENS)

    # Hindsight is the only memory store: local auto memory (per-project MEMORY.md fact
    # files and the remember-flows that feed them) stays off. Enforced, not defaulted —
    # a hand-toggle here would silently fork memory into an unreconciled local store.
    document["autoMemoryEnabled"] = False
    return document


def load_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"refusing to replace unreadable settings file: {path}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"refusing to replace non-object settings file: {path}")
    return parsed


def write_settings(path: Path, document: dict[str, Any]) -> None:
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(rendered)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    args = parse_args()
    command = hook_command(
        args.python.resolve(),
        args.script.absolute(),
        args.env_file.absolute(),
        args.state_dir.absolute(),
    )
    primer_cmd = primer_command(
        args.python.resolve(),
        args.primer_script.absolute(),
        args.env_file.absolute(),
    )
    instructions_cmd = " ".join(
        shlex.quote(argument)
        for argument in (str(args.python.resolve()), str(args.instructions_script.absolute()))
    )
    gate_cmd = " ".join(
        shlex.quote(argument)
        for argument in (
            str(args.python.resolve()),
            str(args.gate_script.absolute()),
            "--env-file",
            str(args.env_file.absolute()),
        )
    )
    try:
        document = load_settings(args.settings)
        merge_settings(
            document,
            command,
            args.script.absolute(),
            primer_cmd,
            args.primer_script.absolute(),
            instructions_cmd,
            args.instructions_script.absolute(),
            gate_cmd,
            args.gate_script.absolute(),
        )
        write_settings(args.settings, document)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"  configured retention, primer, and repo-instruction hooks in {args.settings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
