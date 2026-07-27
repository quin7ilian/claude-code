#!/usr/bin/env python3
"""Inject a cached Hindsight memory primer into each new Claude Code session.

Serves a two-section primer from a local per-project cache and keeps that cache fresh in
the background (stale-while-revalidate):

- `SessionStart` hook: print the cached primer instantly, then spawn a detached refresh
  worker and exit. On a cache miss (first session in a project) build one synchronously
  at low recall budget, cache it, and kick a high-budget upgrade refresh.
- `SessionEnd` hook: spawn a refresh worker, so the cache reflects the session that just
  ended by the time the next session starts.
- `--refresh` worker: rebuild the primer at high recall budget under a per-project lock
  and write it atomically. Runs detached; latency is invisible.

The primer has two sections: standing rules & preferences (the bank's active directives
fetched verbatim plus a dedicated rules recall, so pinned behavior never competes with
topical facts for ranking slots) and project context (a project-scoped recall). Facts
matching known bookkeeping-noise shapes are dropped, and the header carries the
generation time so a session knows the age of what it is holding.

Fail-open everywhere: on any failure the hook prints nothing (or the stale cache) and
exits 0; a session must never be blocked or polluted by a memory-store failure.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from retain_hindsight import (  # noqa: E402
    RetentionError,
    _endpoint,
    default_transport,
    load_retention_config,
    stable_project,
)

DEFAULT_ENV_FILE = "~/.claude/.env"
DEFAULT_CACHE_DIR = "~/.claude/hindsight-primer"
DEFAULT_HTTP_TIMEOUT = 8.0
REFRESH_HTTP_TIMEOUT = 30.0
CACHE_VERSION = 1
RULES_MAX_TOKENS = 600
CONTEXT_MAX_TOKENS = 1200
MAX_DIRECTIVES = 10
MAX_RULES = 6
MAX_CONTEXT_FACTS = 10
MAX_FACT_CHARS = 400

# Known junk-fact shapes: retention/migration bookkeeping and harness surface noise that
# adds nothing a session can act on.
NOISE_RE = re.compile(
    r"opened the file .+ in the IDE"
    r"|\bNote recorded\b"
    r"|\bnote was created\b"
    r"|\b(?:curated |project.)?memory note\b"
    r"|\bMemory note metadata\b"
    r"|migrated into Hindsight"
    r"|memory node '.*' was (?:created|modified)"
    r"|\bReflect Mission\b"
    r"|\bproject -(?:var-)?home-"
    r"|^The project is (?:named )?[\w./-]+\.?$",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(DEFAULT_ENV_FILE).expanduser())
    parser.add_argument("--cache-dir", type=Path, default=Path(DEFAULT_CACHE_DIR).expanduser())
    parser.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cwd", type=Path, default=None)
    return parser.parse_args()


def normalize_project(name: str) -> str:
    """Comparable form of a project identity. Facts retained before project identities
    were stabilized carry path-shaped names (`-var-home-user-Work-src-org-repo`,
    `D--Work-src-org-repo`), so compare on a lowercased dash-joined form and treat a
    suffix match as the same project."""
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def same_project(fact_project: str, current: str) -> bool:
    fact, wanted = normalize_project(fact_project), normalize_project(current)
    if not fact or not wanted:
        return False
    return fact == wanted or fact.endswith(f"-{wanted}")


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_FACT_CHARS:
        text = text[: MAX_FACT_CHARS - 1] + "…"
    return text


def _recall_facts(
    config,
    query: str,
    max_tokens: int,
    budget: str,
    timeout: float,
    transport,
    seen: set[str],
    scope_project: str | None = None,
) -> list[str]:
    """Recall facts for a query, optionally scoped to one project.

    Server-side tag filtering does not restrict results in this deployment, but every
    result carries its provenance (`metadata.project`, `tags`), so scoping is applied
    here: with `scope_project` set, a fact attributed to a different project is dropped,
    while unattributed facts (older sources that predate project metadata) are kept.
    """
    result = transport(
        "POST",
        _endpoint(config, "memories/recall"),
        config.headers,
        {
            "query": query,
            "max_tokens": max_tokens,
            "budget": budget,
            "query_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        timeout,
    )
    facts: list[str] = []
    for entry in result.get("results", []):
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if NOISE_RE.search(text):
            continue
        if scope_project:
            metadata = entry.get("metadata")
            attributed = metadata.get("project") if isinstance(metadata, dict) else None
            if isinstance(attributed, str) and attributed.strip():
                if not same_project(attributed, scope_project):
                    continue
        cleaned = _clean(text)
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        facts.append(cleaned)
    return facts


def _directives(config, timeout: float, transport) -> list[str]:
    result = transport(
        "GET",
        _endpoint(config, "directives?active_only=true"),
        config.headers,
        None,
        timeout,
    )
    names: list[str] = []
    for item in result.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
            names.append(_clean(item["name"]))
        if len(names) >= MAX_DIRECTIVES:
            break
    return names


def build_primer(
    config, project: str, timeout: float, budget: str = "low", transport=default_transport
) -> str:
    seen: set[str] = set()
    directives: list[str] = []
    rules: list[str] = []
    context: list[str] = []

    try:
        directives = _directives(config, timeout, transport)
    except RetentionError:
        pass
    try:
        rules = _recall_facts(
            config,
            "standing rules and user preferences the assistant must always follow: git "
            "workflow (commits, branches, staging), coding conventions, communication "
            f"style, verification habits — globally and for {project}",
            RULES_MAX_TOKENS,
            budget,
            timeout,
            transport,
            seen,
        )[:MAX_RULES]
    except RetentionError:
        pass
    try:
        # Rules are global — a preference stated in one repository applies everywhere — so
        # the rules recall above is deliberately unscoped. Project context is scoped, so a
        # session never opens with another project's state presented as its own.
        context = _recall_facts(
            config,
            f"{project}: current project state, recent decisions and their rationale, "
            "work in progress, unresolved problems, next steps",
            CONTEXT_MAX_TOKENS,
            budget,
            timeout,
            transport,
            seen,
            scope_project=project,
        )[:MAX_CONTEXT_FACTS]
    except RetentionError:
        pass

    if not (directives or rules or context):
        return ""

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"Long-term memory primer for {project} (Hindsight, generated {generated}).",
        "Historical context, not proof of current state — verify against current artifacts.",
        "For deeper or targeted retrieval, call mcp__hindsight__recall.",
    ]
    if directives or rules:
        lines.append("")
        lines.append("## Standing rules and preferences")
        lines.extend(f"- {name}" for name in directives)
        lines.extend(f"- {fact}" for fact in rules)
    if context:
        lines.append("")
        lines.append(f"## {project} context")
        lines.extend(f"- {fact}" for fact in context)
    return "\n".join(lines)


def _cache_path(cache_dir: Path, project: str) -> Path:
    return cache_dir / f"{hashlib.sha256(project.encode()).hexdigest()}.json"


def read_cache(cache_dir: Path, project: str) -> str | None:
    try:
        raw = json.loads(_cache_path(cache_dir, project).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        return None
    primer = raw.get("primer")
    return primer if isinstance(primer, str) and primer else None


def write_cache(cache_dir: Path, project: str, primer: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(cache_dir, 0o700)
    payload = {
        "version": CACHE_VERSION,
        "project": project,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primer": primer,
    }
    path = _cache_path(cache_dir, project)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=cache_dir)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def kick_refresh(args: argparse.Namespace, cwd: str) -> None:
    """Spawn a detached refresh worker. Its stdio is fully closed off so the hook's
    stdout is never held open by the child."""
    try:
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--refresh",
                "--cwd",
                cwd,
                "--env-file",
                str(args.env_file),
                "--cache-dir",
                str(args.cache_dir),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def run_refresh(args: argparse.Namespace) -> int:
    if args.cwd is None:
        return 0
    project = stable_project(str(args.cwd))
    if not project:
        return 0
    try:
        args.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = args.cache_dir / f"{hashlib.sha256(project.encode()).hexdigest()}.lock"
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return 0
    with os.fdopen(lock_descriptor, "r+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        try:
            config = load_retention_config(args.env_file)
            primer = build_primer(config, project, REFRESH_HTTP_TIMEOUT, budget="high")
            if primer:
                write_cache(args.cache_dir, project, primer)
        except Exception:
            pass
    return 0


def main() -> int:
    args = parse_args()
    if args.refresh:
        return run_refresh(args)

    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(hook_input, dict):
        return 0
    event = hook_input.get("hook_event_name")
    cwd = hook_input.get("cwd")
    if event not in ("SessionStart", "SessionEnd") or not isinstance(cwd, str) or not cwd:
        return 0
    if event == "SessionEnd":
        kick_refresh(args, cwd)
        return 0

    project = stable_project(cwd)
    try:
        cached = read_cache(args.cache_dir, project)
    except Exception:
        cached = None
    if cached:
        print(cached)
        kick_refresh(args, cwd)
        return 0

    # Cache miss: build once synchronously at low budget, then upgrade in the background.
    try:
        config = load_retention_config(args.env_file)
        primer = build_primer(config, project, args.http_timeout, budget="low")
    except (RetentionError, Exception):
        primer = ""
    if primer:
        print(primer)
        try:
            write_cache(args.cache_dir, project, primer)
        except Exception:
            pass
    kick_refresh(args, cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
