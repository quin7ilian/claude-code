#!/usr/bin/env python3
"""Announce the gated documents at the start of each Claude Code session.

Claude Code auto-loads `CLAUDE.md` but not `AGENTS.md`, the cross-vendor standard, so a
repository whose instructions live in `AGENTS.md` would start every session with no sign
of them. This `SessionStart` hook prints a pointer: the absolute path, the section
headings, and notice that writes are gated until the file is read. It names the
standing-rules document alongside it, since writes are gated on that too and an agent that
learns of it only from a denial spends its first write finding out.

It deliberately prints pointers rather than contents. Injected rules are received passively
and skimmed; a rule the agent went and read is one it acts on. The `PreToolUse` gate makes
those reads mandatory before any write, so a pointer is enough to make each document
discoverable while the read stays an act the agent performs.

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


MAX_HEADINGS = 24
INSTRUCTION_FILENAME = "AGENTS.md"
HEADING_RE = re.compile(r"^#{1,3} \S")
# A root CLAUDE.md that imports AGENTS.md already gets it loaded natively.
IMPORT_RE = re.compile(r"^\s*@(?:\./)?AGENTS\.md\s*$", re.M)
# Repository roots: a VCS directory, or a lone AGENTS.md at the top of a project.
ROOT_MARKERS = (".git", ".hg", ".svn", ".jj")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-headings", type=int, default=MAX_HEADINGS)
    # Resolved lazily against the primer's own default, which cannot be imported here.
    parser.add_argument("--cache-dir", type=Path, default=None)
    return parser.parse_args()


def rules_document(root: Path, cache_dir: Path | None = None) -> Path | None:
    """The standing-rules document for this repository, when one has been recalled.

    Imported inside the function because `prime_hindsight` imports this module for
    `find_repo_root`; a module-scope import back into it would be circular.
    """
    try:
        from prime_hindsight import DEFAULT_CACHE_DIR, rules_path
        from retain_hindsight import stable_project
    except ImportError:
        return None
    directory = cache_dir if cache_dir is not None else Path(DEFAULT_CACHE_DIR).expanduser()
    try:
        document = rules_path(directory, stable_project(str(root)))
    except Exception:
        return None
    return document if document.is_file() else None


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


def section_headings(text: str, limit: int = MAX_HEADINGS) -> list[str]:
    headings = [line.strip() for line in text.splitlines() if HEADING_RE.match(line)]
    return headings[:limit]


def build_injection(cwd: str, max_chars: int = 0, cache_dir: Path | None = None) -> str:
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

    lines = [
        f"This repository has instructions at {instructions}, which Claude Code does not "
        "auto-load.",
        "They are binding: they outrank general practice and your own assumptions, and "
        "every brief you send to a subagent or external reviewer must require reading and "
        "complying with them.",
        "",
        "Read the file in full with the Read tool before you write anything here — file "
        "writes are gated on it, and a partial read does not count. Re-read it if it "
        "changes or if it falls far behind in the conversation.",
    ]
    headings = section_headings(text)
    if headings:
        lines.append("")
        lines.append(f"It covers ({len(text):,} characters):")
        lines.extend(f"  {heading}" for heading in headings)

    rules = rules_document(root, cache_dir)
    if rules is not None:
        lines.append("")
        lines.append(
            f"Your standing rules and preferences are at {rules}, recalled from long-term "
            "memory. Writes are gated on having read that file too — the memory primer "
            "carries the same rules, but holding them in context is not reading them."
        )
    return "\n".join(lines)


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
        injection = build_injection(cwd, cache_dir=args.cache_dir)
    except Exception:
        return 0
    if injection:
        print(injection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
