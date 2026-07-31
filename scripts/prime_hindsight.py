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

The primer has two sections: standing rules & preferences (the bank's active directives,
verbatim) and project context (a project-scoped recall). The header carries the generation
time so a session knows the age of what it is holding.

Rules come from directives alone. A recall over rule-shaped language cannot separate a
standing rule from a fact about one, so it returns notes about the rules — and about this
primer's own construction — ranked alongside the rules themselves. Directives are the
curated set; promoting a preference into one is how it reaches the gate.

The rules section is also written to disk on its own, at `rules_path()`, because the write
gate requires an agent to have *read* it — rules that merely sit in a session's context get
skimmed. A confirmed-empty bank retires that document; a failed fetch leaves it alone, since
the gate reads an absent document as "no standing rules apply".

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

from inject_repo_instructions import find_repo_root  # noqa: E402
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
CONTEXT_MAX_TOKENS = 1200
MAX_DIRECTIVES = 10
MAX_CONTEXT_FACTS = 10
MAX_FACT_CHARS = 400

# What belongs in the primer is Hindsight's judgment, expressed through the query it is
# asked. Pattern-matching over returned facts cannot weigh meaning, and silently discards
# real rules along with the noise.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(DEFAULT_ENV_FILE).expanduser())
    parser.add_argument("--cache-dir", type=Path, default=Path(DEFAULT_CACHE_DIR).expanduser())
    parser.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cwd", type=Path, default=None)
    return parser.parse_args()


def project_identity(cwd: str) -> str:
    """The project a working directory belongs to.

    Resolved from the repository root rather than the directory itself, so a session
    started in a subdirectory names the same project as one started at the top — and so
    the gate, which resolves the repository from the file being written, agrees.
    """
    root = find_repo_root(Path(cwd))
    return stable_project(str(root) if root is not None else cwd)


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


def _collapse(text: str) -> str:
    """One line, so a multi-line value cannot break the list it is rendered into."""
    return re.sub(r"\s+", " ", text).strip()


def _clean(text: str) -> str:
    text = _collapse(text)
    if len(text) > MAX_FACT_CHARS:
        text = text[: MAX_FACT_CHARS - 1] + "…"
    return text


def _listing(result: dict, key: str) -> list:
    """The list under `key`, or `RetentionError` when the response is not shaped that way.

    A malformed payload is a failed fetch, not an empty one. An empty result is a fact about
    the bank that callers act on — the rules document is deleted on it — so the two must
    never be conflated. An absent key is malformed rather than empty: a well-formed response
    carries the collection even when it holds nothing.
    """
    if key not in result:
        raise RetentionError(f"malformed response: {key} is absent")
    value = result[key]
    if not isinstance(value, list):
        raise RetentionError(f"malformed response: {key} is not a list")
    return value


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
    for entry in _listing(result, "results"):
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip():
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
    for item in _listing(result, "items"):
        # Strict, because skipping an unreadable entry would shrink the set and a set that
        # shrinks to nothing is indistinguishable from a bank holding no directives — which
        # deletes the gated document. A shape change must fail, not silently empty it.
        if not isinstance(item, dict):
            raise RetentionError("malformed response: directive entry is not an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RetentionError("malformed response: directive has no usable name")
        # Collapsed but never truncated: a directive name is the whole rule, and the gated
        # document is the only place an agent reads it.
        names.append(_collapse(name))
        if len(names) >= MAX_DIRECTIVES:
            break
    return names


def collect_sections(
    config, project: str, timeout: float, budget: str, transport
) -> tuple[list[str] | None, list[str]]:
    """Directives and project context. Each fails open alone.

    `directives` is `None` when the fetch failed and `[]` when it succeeded against a bank
    that holds none. Only the second is grounds for deleting the rules document.
    """
    seen: set[str] = set()
    directives: list[str] | None = None
    context: list[str] = []

    try:
        directives = _directives(config, timeout, transport)
    except RetentionError:
        pass
    try:
        # Every recall result carries its provenance, so facts attributed to another
        # project are dropped and a session never opens with another project's state.
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

    return directives, context


def build_primer(
    config, project: str, timeout: float, budget: str = "low", transport=default_transport
) -> str:
    directives, context = collect_sections(config, project, timeout, budget, transport)
    return render_primer(project, directives or [], context)


def render_primer(project: str, directives: list[str], context: list[str]) -> str:
    if not (directives or context):
        return ""

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"Long-term memory primer for {project} (Hindsight, generated {generated}).",
        "Historical context, not proof of current state — verify against current artifacts.",
        "For deeper or targeted retrieval, call mcp__hindsight__recall.",
    ]
    if directives:
        lines.append("")
        lines.append("## Standing rules and preferences")
        lines.extend(f"- {name}" for name in directives)
    if context:
        lines.append("")
        lines.append(f"## {project} context")
        lines.extend(f"- {fact}" for fact in context)
    return "\n".join(lines)


def _cache_path(cache_dir: Path, project: str) -> Path:
    return cache_dir / f"{hashlib.sha256(project.encode()).hexdigest()}.json"


def rules_path(cache_dir: Path, project: str) -> Path:
    """The standing-rules document for a project.

    Materialized as a file so an agent can read it: rules that merely sit in context get
    skimmed, and writes are gated on having read this one.
    """
    return cache_dir / f"{hashlib.sha256(project.encode()).hexdigest()}.rules.md"


def render_rules(project: str, directives: list[str]) -> str:
    if not directives:
        return ""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Standing rules and preferences ({project}, recalled {generated})",
        "",
        "These are binding for every project. File writes are gated on having read them.",
        "",
    ]
    lines.extend(f"- {name}" for name in directives)
    return "\n".join(lines) + "\n"


def sync_rules_document(cache_dir: Path, project: str, directives: list[str] | None) -> None:
    """Bring the gated rules document in line with the bank.

    `None` means the directive fetch failed, so the existing document is left untouched —
    the gate reads an absent document as "no standing rules apply", making deletion on a
    transient error worse than serving a stale copy. An empty list is a confirmed empty
    bank, so a document left over from withdrawn directives is removed.
    """
    if directives is None:
        return
    document = render_rules(project, directives)
    if document:
        write_rules(cache_dir, project, document)
        return
    try:
        rules_path(cache_dir, project).unlink(missing_ok=True)
    except OSError:
        pass


def write_rules(cache_dir: Path, project: str, document: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(cache_dir, 0o700)
    path = rules_path(cache_dir, project)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=cache_dir)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(document)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


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
    project = project_identity(str(args.cwd))
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
            directives, context = collect_sections(
                config, project, REFRESH_HTTP_TIMEOUT, "high", default_transport
            )
            primer = render_primer(project, directives or [], context)
            if primer:
                write_cache(args.cache_dir, project, primer)
            sync_rules_document(args.cache_dir, project, directives)
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

    project = project_identity(cwd)
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
        directives, context = collect_sections(
            config, project, args.http_timeout, "low", default_transport
        )
        primer = render_primer(project, directives or [], context)
    except (RetentionError, Exception):
        directives, primer = None, ""
    if primer:
        print(primer)
        try:
            write_cache(args.cache_dir, project, primer)
        except Exception:
            pass
    # Independent of the primer: an empty bank still retires an obsolete rules document,
    # and an empty primer is not evidence that the directive fetch failed.
    try:
        sync_rules_document(args.cache_dir, project, directives)
    except Exception:
        pass
    kick_refresh(args, cwd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
