#!/usr/bin/env python3
"""Require the repository's AGENTS.md to have been read before any file is written.

Runs as the `PreToolUse` hook for the writing tools. When the target file belongs to a
repository that has an `AGENTS.md`, the write is denied until the acting agent has read
that file — completely, in its current form, and recently enough to still be in effective
context.

Compliance is derived from the agent's own transcript: it is the source of truth for what
that agent read, it cannot drift, and it leaves nothing to clean up.

The live window is defined by context, never by transcript size. It starts after the most
recent compaction — an explicit compact-summary record, or a drop in context size — and
after the point where the context was more than the budget below its current size. A fresh
session, or one that has just compacted, therefore has no prior read and is gated until
the file is read.

Two documents are gated. The repository's `AGENTS.md` must have been read completely and
in its current form. The standing-rules document recalled from long-term memory is gated
on presence of a read alone: it is regenerated in the background, so requiring its content
to still match would re-gate an agent every time a refresh landed. When the gate is about
to ask for it, a refresh is spawned first, so the read it prompts returns current memory.

A read of `AGENTS.md` qualifies when all of these hold:

- it used the `Read` tool on the repository's `AGENTS.md`, with no `offset` or `limit`;
- its result is the one produced by that call, correlated by `tool_use_id`;
- the content it returned is exactly the file's current content, so any edit to
  `AGENTS.md` re-gates every agent;
- it still sits in the live window: after the most recent compaction, and within
  `--max-context-growth` tokens of the current context size.

The hook prints a decision only to deny. Staying silent leaves the normal permission flow
untouched; emitting `allow` would auto-approve the write and bypass permission prompts.

Fail-open: any error, missing evidence, or unreadable state stays silent and lets the
write proceed. A gate that can deadlock a session is worse than the problem it solves.
Set `CLAUDE_SKIP_AGENTS_GATE=1` to disable it entirely.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inject_repo_instructions import INSTRUCTION_FILENAME, find_repo_root  # noqa: E402
from prime_hindsight import DEFAULT_CACHE_DIR, rules_path  # noqa: E402
from retain_hindsight import stable_project  # noqa: E402

GATED_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PATH_KEYS = ("file_path", "notebook_path", "path")
# Staleness is measured in context tokens, not transcript bytes: tool output inflates the
# transcript far more than it occupies the agent's context, and it is the context the
# agent is reasoning over. Compaction discards the read outright, so it is stale at once.
DEFAULT_MAX_CONTEXT_GROWTH = 200_000
# How much of the transcript tail to parse per attempt while locating the window
# boundary. It affects only how many reads that search takes, never the decision.
INITIAL_SPAN_BYTES = 1_000_000
# A whole-file Read past this many lines comes back paginated, which no unranged read can
# satisfy; such a file cannot be gated without deadlocking the agent.
READ_LINE_LIMIT = 2000
DISABLE_ENV = "CLAUDE_SKIP_AGENTS_GATE"
DEFAULT_ENV_FILE = "~/.claude/.env"
# Read renders each line as "<padding><line number><separator><content>".
NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)[\t:](.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-context-growth", type=int, default=DEFAULT_MAX_CONTEXT_GROWTH)
    parser.add_argument("--cache-dir", type=Path, default=Path(DEFAULT_CACHE_DIR).expanduser())
    parser.add_argument("--env-file", type=Path, default=Path(DEFAULT_ENV_FILE).expanduser())
    return parser.parse_args()


def read_index_of(records: list[dict], path: Path) -> int | None:
    """Index of the most recent `Read` of `path`, if the agent read it at all.

    Presence only: the standing-rules document is regenerated from memory in the
    background, so requiring its content to still match would re-gate an agent through no
    fault of its own every time a refresh landed. It expires on context growth like any
    other read, which the caller checks.
    """
    wanted = str(path)
    for index in range(len(records) - 1, -1, -1):
        for block in ((records[index].get("message") or {}).get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Read":
                continue
            candidate = str((block.get("input") or {}).get("file_path") or "")
            if candidate and os.path.abspath(candidate) == wanted:
                return index
    return None


def refresh_rules(cwd: str, cache_dir: Path, env_file: Path) -> None:
    """Rebuild the standing-rules document in the background.

    Spawned as the gate is about to ask for a read, so the read it prompts returns
    current memory rather than whatever was recalled at session start. Best effort: a
    failure here must never affect the decision.
    """
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve().parent / "prime_hindsight.py"),
                "--refresh",
                "--cwd",
                cwd,
                "--cache-dir",
                str(cache_dir),
                "--env-file",
                str(env_file),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        # Best effort only: a refresh that cannot start must not change the decision.
        pass


def context_size(record: dict) -> int | None:
    """Total context the model held for this record, in tokens."""
    usage = (record.get("message") or {}).get("usage")
    if not isinstance(usage, dict):
        return None
    total = 0
    for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            total += value
    return total or None


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def target_path(hook_input: dict) -> Path | None:
    """The file the tool is about to write, resolved against `cwd` when relative."""
    payload = hook_input.get("tool_input")
    if not isinstance(payload, dict):
        return None
    for key in PATH_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if not path.is_absolute():
                cwd = hook_input.get("cwd")
                if isinstance(cwd, str) and cwd:
                    path = Path(cwd) / path
            return path
    return None


def agent_transcript(hook_input: dict) -> Path | None:
    """The transcript whose reads count for this agent.

    Inside a subagent, `transcript_path` names the parent session, so the child's own
    transcript is derived from `agent_id`. A parent's read must never satisfy a child, so
    when the derived path is unavailable this returns None (fail open) rather than
    falling back to the parent.
    """
    value = hook_input.get("transcript_path")
    if not isinstance(value, str) or not value:
        return None
    transcript = Path(value)
    agent_id = hook_input.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        derived = transcript.parent / transcript.stem / "subagents" / f"agent-{agent_id}.jsonl"
        return derived if derived.is_file() else None
    return transcript if transcript.is_file() else None


def read_output_matches(read_text: str, disk_text: str) -> bool:
    """True when a Read result is exactly the file's current content.

    Anchors on Read's own line numbering: every line must carry its sequential number, so
    file content that itself begins with digits and a tab cannot be mistaken for the
    prefix. File whitespace is preserved on both sides.
    """
    if not read_text:
        return False
    # Read numbers every element of the newline split, so a file ending in a newline
    # renders one final numbered-but-empty line. Keep it on the disk side to match.
    disk_lines = disk_text.split("\n")
    read_lines = read_text.split("\n")
    if read_lines and read_lines[-1] == "":
        # A newline terminating the result payload itself, not a rendered file line.
        read_lines = read_lines[:-1]
    if len(read_lines) != len(disk_lines):
        return False
    for index, (rendered, actual) in enumerate(zip(read_lines, disk_lines), start=1):
        match = NUMBERED_LINE_RE.match(rendered)
        if not match or int(match.group(1)) != index or match.group(2) != actual:
            return False
    return True


def _result_text(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("file", "content", "text"):
            if key in payload:
                return _result_text(payload[key])
    if isinstance(payload, list):
        return "\n".join(_result_text(item) for item in payload)
    return ""


def _parse_tail(transcript: Path, span: int) -> list[dict] | None:
    """Records from the last `span` bytes, or None when unreadable or undecodable."""
    try:
        size = transcript.stat().st_size
        with transcript.open("rb") as handle:
            if span < size:
                handle.seek(size - span)
                handle.readline()  # discard the partial record at the seek point
            payload = handle.read()
    except OSError:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def window_start(records: list[dict]) -> int:
    """Index where the live window begins: just after the most recent compaction.

    Compaction discards what came before, so the session effectively starts again there.
    It shows up two ways, and they cut at different places: an explicit compact-summary
    record is itself pre-compaction, so the window starts after it; a drop in context
    size is first observed *on* the first post-compaction record, which may carry the
    read that follows it, so the window starts at that record.
    """
    start = 0
    previous: int | None = None
    for index, record in enumerate(records):
        if record.get("isCompactSummary") is True:
            start = index + 1
            # The drop that follows is this same compaction, not another one.
            previous = None
            continue
        size = context_size(record)
        if size is None:
            continue
        if previous is not None and size < previous:
            start = index
        previous = size
    return start


def within_growth(records: list[dict], index: int, max_growth: int) -> bool:
    """Whether a read at `index` is still within the context-growth budget."""
    at_read = context_at(records, index)
    current = current_context(records)
    if at_read is None or current is None:
        return True
    return current - at_read <= max_growth


def context_at(records: list[dict], index: int) -> int | None:
    """Context size in force at `index`: the nearest usage sample at or before it."""
    for record in reversed(records[: index + 1]):
        size = context_size(record)
        if size is not None:
            return size
    for record in records[index + 1:]:
        size = context_size(record)
        if size is not None:
            return size
    return None


def current_context(records: list[dict]) -> int | None:
    for record in reversed(records):
        size = context_size(record)
        if size is not None:
            return size
    return None


def covers_live_window(records: list[dict], max_growth: int) -> bool:
    """True when the parsed records reach back past the whole live window.

    Once the earliest sample sits more than `max_growth` below the current size, any read
    older than it is stale anyway, so there is nothing further back worth finding.
    """
    current = current_context(records)
    if current is None:
        return False
    for record in records:
        size = context_size(record)
        if size is not None:
            # A read at exactly `current - max_growth` is still fresh, so the window is
            # only complete once the earliest sample sits strictly below it.
            return size < current - max_growth
    return False


def live_window(transcript: Path, max_growth: int) -> list[dict] | None:
    """Records since the most recent compaction, reaching back past the live window.

    The window is defined by context, never by transcript size — the file is read from
    the end in growing spans purely until the evidence is complete, which is when a
    compaction is found, the covered context exceeds the budget, or the file is
    exhausted. Returns None when the transcript cannot be read, which fails open.
    """
    try:
        size = transcript.stat().st_size
    except OSError:
        return None
    span = min(size, INITIAL_SPAN_BYTES) or size
    while True:
        records = _parse_tail(transcript, span)
        if records is None:
            return None
        start = window_start(records)
        if start:
            return records[start:]
        if covers_live_window(records, max_growth) or span >= size:
            return records
        span = min(size, span * 4)


def qualifying_read_ids(records: list[dict], instructions: Path) -> set[str]:
    """Ids of unranged `Read` calls on the instruction file.

    Any `offset` or `limit` key disqualifies a call, present-or-absent rather than by
    truthiness: `limit=0` is still a ranged read.
    """
    wanted = str(instructions)
    identifiers: set[str] = set()
    for record in records:
        for block in ((record.get("message") or {}).get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Read":
                continue
            payload = block.get("input") or {}
            path = str(payload.get("file_path") or "")
            if not path:
                continue
            if os.path.abspath(path) != wanted:
                continue
            if "offset" in payload or "limit" in payload:
                continue
            identifier = block.get("id")
            if isinstance(identifier, str) and identifier:
                identifiers.add(identifier)
    return identifiers


def qualifying_read_index(
    records: list[dict], instructions: Path, disk_text: str
) -> int | None:
    """Index of the most recent record proving a complete, current read, if any."""
    identifiers = qualifying_read_ids(records, instructions)
    if not identifiers:
        return None
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        # A result belongs to a call only via its tool_use_id; the structured
        # `toolUseResult` payload is accepted only alongside that correlation.
        matched = [
            block
            for block in ((record.get("message") or {}).get("content") or [])
            if isinstance(block, dict)
            and block.get("type") == "tool_result"
            and block.get("tool_use_id") in identifiers
        ]
        if not matched:
            continue
        candidates = [_result_text(block.get("content")) for block in matched]
        structured = record.get("toolUseResult")
        if structured is not None:
            candidates.append(_result_text(structured))
        if any(read_output_matches(text, disk_text) for text in candidates):
            return index
    return None


TRUNCATION_KEYS = ("truncatedByTokenCap", "truncated", "isTruncated")


def _is_truncated(payload: object) -> bool:
    """Whether a Read result reports that it returned only part of the file."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in TRUNCATION_KEYS and value:
                return True
            if _is_truncated(value):
                return True
    if isinstance(payload, list):
        return any(_is_truncated(item) for item in payload)
    return False


def read_cannot_prove(records: list[dict], instructions: Path) -> bool:
    """True when the file was read but the result can never match its content.

    Read paginates files past its line or token cap and can return an empty view, and no
    amount of re-reading turns such a result into proof — denying would be a livelock.
    """
    identifiers = qualifying_read_ids(records, instructions)
    if not identifiers:
        return False
    for record in records:
        if record.get("toolUseResult") is not None and _is_truncated(record.get("toolUseResult")):
            return True
        for block in ((record.get("message") or {}).get("content") or []):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") not in identifiers:
                continue
            if _is_truncated(block.get("content")):
                return True
            text = _result_text(block.get("content"))
            if not any(NUMBERED_LINE_RE.match(line) for line in text.split("\n")[:5]):
                return True
    return False


def evaluate(
    hook_input: dict,
    max_context_growth: int = DEFAULT_MAX_CONTEXT_GROWTH,
    cache_dir: Path | None = None,
    env_file: Path | None = None,
) -> dict | None:
    """The deny decision, or None to stay silent and leave permissions untouched."""
    if os.environ.get(DISABLE_ENV) == "1":
        return None
    if hook_input.get("tool_name") not in GATED_TOOLS:
        return None

    target = target_path(hook_input)
    if target is None:
        # The governing repository comes from the file being written; without a target
        # there is nothing to judge.
        return None
    root = find_repo_root(target if target.is_dir() else target.parent)
    if root is None:
        return None
    instructions = (root / INSTRUCTION_FILENAME).resolve()
    try:
        disk_bytes = instructions.read_bytes()
    except OSError:
        return None
    if not disk_bytes.strip():
        return None
    try:
        disk_text = disk_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Content cannot be compared faithfully, so the gate cannot judge it.
        return None
    if len(disk_text.split("\n")) > READ_LINE_LIMIT:
        # An unranged Read would be paginated, leaving no way to satisfy the gate.
        return None
    if "\r\n" in disk_text:
        # Read normalizes line endings, so a CRLF file cannot be proven identical.
        return None

    transcript = agent_transcript(hook_input)
    if transcript is None:
        return None
    records = live_window(transcript, max_context_growth)
    if records is None:
        return None

    instructions_ok = False
    read_index = qualifying_read_index(records, instructions, disk_text)
    if read_index is not None and within_growth(records, read_index, max_context_growth):
        instructions_ok = True
    if not instructions_ok and read_cannot_prove(records, instructions):
        # The file was read but the result can never match, so re-reading would not help.
        instructions_ok = True

    # The standing-rules document is gated the same way, on presence of a read alone.
    # Absent (no memory store, fresh project) it simply does not apply.
    cache_dir = cache_dir or Path(DEFAULT_CACHE_DIR).expanduser()
    rules_document = rules_path(cache_dir, stable_project(str(root)))
    if rules_document.is_file():
        rules_index = read_index_of(records, rules_document.resolve())
        rules_ok = rules_index is not None and within_growth(
            records, rules_index, max_context_growth
        )
    else:
        rules_ok = True

    if instructions_ok and rules_ok:
        return None

    if not rules_ok:
        # The read this prompts should return current memory, not session-start memory.
        cwd = hook_input.get("cwd")
        if isinstance(cwd, str) and cwd:
            refresh_rules(cwd, cache_dir, env_file or Path(DEFAULT_ENV_FILE).expanduser())

    wanted: list[str] = []
    if not instructions_ok:
        if qualifying_read_ids(records, instructions):
            why = "it has changed since you read it"
        else:
            why = "it is not in your current context"
        wanted.append(
            f"- {instructions} — in full with the Read tool, no offset or limit ({why})"
        )
    if not rules_ok:
        wanted.append(
            f"- {rules_document} — your standing rules and preferences, recalled from "
            "long-term memory"
        )

    return _deny(
        "Checkpoint, not a refusal — this write is fine to make, and nothing about it is "
        "wrong. The rules that govern it just need to be in front of you first.\n\n"
        "Read these, then retry this exact edit and it will go through:\n"
        + "\n".join(wanted)
        + "\n\nPlease do not route around this by writing through Bash (sed, printf, "
        "tee, heredocs). That skips the rules themselves, not merely this check — and "
        "the point is that you hold them while you work, not that you satisfy a gate."
    )


def main() -> int:
    args = parse_args()
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(hook_input, dict):
        return 0
    try:
        decision = evaluate(
            hook_input, args.max_context_growth, args.cache_dir, args.env_file
        )
    except Exception:
        decision = None
    if decision is not None:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
