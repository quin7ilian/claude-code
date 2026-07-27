#!/usr/bin/env python3
"""Inject the repository's AGENTS.md into each new Claude Code session's context.

Claude Code auto-loads `CLAUDE.md` but not `AGENTS.md`, the cross-vendor standard, so a
repository whose instructions live in `AGENTS.md` starts every session with those rules
absent — an agent cannot follow a file it never received. This `SessionStart` hook closes
that gap: it locates the repository root from the session's working directory, reads
`AGENTS.md`, and prints it, giving repository instructions the same ambient status
`CLAUDE.md` has natively.

Skipped when the repository has no `AGENTS.md`, or when a root `CLAUDE.md` already imports
it (`@AGENTS.md`), which means Claude Code loads it natively already.

Fail-open: on any error it prints nothing and exits 0.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


DEFAULT_MAX_CHARS = 40000
INSTRUCTION_FILENAME = "AGENTS.md"
# A root CLAUDE.md that imports AGENTS.md already gets it loaded natively.
IMPORT_RE = re.compile(r"^\s*@(?:\./)?AGENTS\.md\s*$", re.M)
# Repository roots: a VCS directory, or a lone AGENTS.md at the top of a project.
ROOT_MARKERS = (".git", ".hg", ".svn", ".jj")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    return parser.parse_args()


def find_repo_root(start: Path) -> Path | None:
    """Nearest ancestor containing a VCS marker; falls back to the nearest ancestor with
    an AGENTS.md so non-VCS project directories still work."""
    try:
        start = start.resolve()
    except OSError:
        return None
    fallback: Path | None = None
    for directory in (start, *start.parents):
        if any((directory / marker).exists() for marker in ROOT_MARKERS):
            return directory
        if fallback is None and (directory / INSTRUCTION_FILENAME).is_file():
            fallback = directory
    return fallback


def already_loaded_natively(root: Path) -> bool:
    claude_md = root / "CLAUDE.md"
    try:
        return bool(IMPORT_RE.search(claude_md.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False


def build_injection(cwd: str, max_chars: int) -> str:
    root = find_repo_root(Path(cwd))
    if root is None:
        return ""
    instructions = root / INSTRUCTION_FILENAME
    try:
        text = instructions.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text or already_loaded_natively(root):
        return ""
    truncated = ""
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = (
            f"\n\n[Truncated at {max_chars} characters — read {instructions} in full "
            "before relying on the omitted sections.]"
        )
    return (
        f"Repository instructions from {instructions} (injected at session start because "
        "Claude Code does not auto-load AGENTS.md).\n"
        "These are binding for work in this repository: they outrank general practice and "
        "your own assumptions, and every brief you send to a subagent or external reviewer "
        "must require reading and complying with them.\n\n"
        f"<repository-instructions path=\"{instructions}\">\n{text}{truncated}\n"
        "</repository-instructions>"
    )


def main() -> int:
    args = parse_args()
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(hook_input, dict):
        return 0
    if hook_input.get("hook_event_name") != "SessionStart":
        return 0
    cwd = hook_input.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return 0
    try:
        injection = build_injection(cwd, args.max_chars)
    except Exception:
        return 0
    if injection:
        print(injection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
