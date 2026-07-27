#!/usr/bin/env python3
"""Retain completed Claude Code turns in Hindsight without blocking the turn.

Runs as the Claude Code `Stop` and `SessionEnd` hook: reads the hook JSON from stdin,
extracts the turns whose content has not been retained yet, and submits them to the
Hindsight REST API as one document per turn (`document_id` derived from session + prompt
id, `update_mode: replace`, so retries are idempotent).

Retention is self-healing: the transcript is written asynchronously, so a hook firing can
observe a turn before its final records are flushed. Each submission records a content
hash per turn, and any turn whose current content no longer matches its submitted hash is
resubmitted — the replace-mode document converges to the turn's full content on a later
firing. Fail-open by design: it must never prevent the turn from completing.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid


STATE_VERSION = 2
USER_AGENT = "claude-code-hindsight-retention/1"
DEFAULT_HTTP_TIMEOUT = 3.0
DEFAULT_ENV_FILE = "~/.claude/.env"
DEFAULT_STATE_DIR = "~/.claude/hindsight-retention"

REQUIRED_ENV_KEYS = ("HINDSIGHT_API_URL", "HINDSIGHT_API_KEY", "HINDSIGHT_BANK_ID")
OPTIONAL_ENV_KEYS = ("HINDSIGHT_USER_TAG",)

# Record-level metadata that marks harness traffic rather than conversation: skill/meta
# injections, subagent sidechains, compaction summaries, API error echoes, and
# transcript-only visibility records.
FILTER_FLAGS = (
    "isMeta",
    "isSidechain",
    "isCompactSummary",
    "isApiErrorMessage",
    "isVisibleInTranscriptOnly",
)

# Claude Code records slash-command echoes, local-command output, and background-task
# notifications as ordinary user records with no metadata marker — the only signal is the
# wrapper tag. Narrow allowlist: those exact tags at the start, a system-notification
# preamble, or a loop sentinel that is the whole message. Deliberately NOT "any leading
# tag", which would eat real user prose containing HTML snippets.
HARNESS_TAG_RE = re.compile(
    r"^\s*(?:<<[a-z0-9-]+>>\s*$"
    r"|\[SYSTEM NOTIFICATION\b"
    r"|</?(?:command-name|command-message|command-args|local-command-stdout"
    r"|local-command-caveat|task-notification)\b)",
    re.I,
)

# IDE context (open file, selection) is prepended to real user messages inside the same
# record — strip the leading blocks and keep the user's own prose.
IDE_CONTEXT_RE = re.compile(
    r"^\s*<(ide_opened_file|ide_selection)>.*?</\1>\s*",
    re.S,
)

PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
    re.DOTALL,
)
AUTHORIZATION_PATTERN = re.compile(
    r"(?i)(\bauthorization\s*[:=]\s*bearer\s+)[^\s,;\"']+"
)
BEARER_PATTERN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{16,}")
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b"
    r"\s*[:=]\s*)([\"']?)([^\s,;\"'}]+)([\"']?)"
)
TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{16,}|"
    r"github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,})"
)


class RetentionError(Exception):
    """A safe-to-report retention failure with no credential or payload content."""


@dataclass(frozen=True)
class RetentionConfig:
    api_base_url: str
    bank_id: str
    headers: dict[str, str]
    user_tag: str = ""


@dataclass(frozen=True)
class Message:
    role: str
    phase: str
    text: str


Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, float], dict[str, Any]
]


class NoRedirectHandler(HTTPRedirectHandler):
    """Do not forward Hindsight credentials across HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(DEFAULT_ENV_FILE).expanduser())
    parser.add_argument("--state-dir", type=Path, default=Path(DEFAULT_STATE_DIR).expanduser())
    parser.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _validated_header(name: str, value: str) -> tuple[str, str]:
    if not name or any(character in name for character in "\r\n:"):
        raise RetentionError("configuration: invalid HTTP header name")
    if "\r" in value or "\n" in value:
        raise RetentionError("configuration: invalid HTTP header value")
    return name, value


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines: `export ` prefixes, quoted values (inline `#` preserved),
    unquoted inline ` #` comments. Missing file is an empty mapping — required keys are
    enforced by the caller, which also lets the process environment win."""
    values: dict[str, str] = {}
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        stripped = value.strip()
        if stripped[:1] in ("'", '"'):
            # Quoted: literal content up to the matching close quote; a '#' inside the
            # quotes is preserved, anything after the close quote is ignored.
            q = stripped[0]
            end = stripped.find(q, 1)
            value = stripped[1:end] if end != -1 else stripped[1:]
        else:
            # Unquoted: an inline ' #' (or a leading '#') starts a comment. Search the RAW
            # value so `KEY=   # note` becomes "" not "# note".
            cut = value.find(" #")
            value = (value[:cut] if cut != -1 else value).strip()
            if value.startswith("#"):
                value = ""
        if key:
            values[key] = value
    return values


def _api_base(url: str) -> str:
    """Normalize HINDSIGHT_API_URL into the REST base: require http(s), strip a trailing
    `/mcp` segment (tolerates the MCP endpoint URL being pasted) and trailing slashes."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise RetentionError("configuration: Hindsight URL must use HTTP or HTTPS")
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and segments[-1] == "mcp":
        segments = segments[:-1]
    base_path = "/" + "/".join(segments) if segments else ""
    return urlunsplit((parts.scheme, parts.netloc, base_path, parts.query, ""))


def load_retention_config(env_path: Path) -> RetentionConfig:
    stored = parse_env_file(env_path)
    values = {
        key: (os.environ.get(key) or stored.get(key) or "").strip()
        for key in REQUIRED_ENV_KEYS
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RetentionError(f"configuration: {', '.join(missing)} not set")

    headers = dict(
        (
            _validated_header("Authorization", f"Bearer {values['HINDSIGHT_API_KEY']}"),
            _validated_header("X-Bank-Id", values["HINDSIGHT_BANK_ID"]),
        )
    )
    user_tag = (
        os.environ.get("HINDSIGHT_USER_TAG") or stored.get("HINDSIGHT_USER_TAG") or ""
    ).strip()
    return RetentionConfig(
        api_base_url=_api_base(values["HINDSIGHT_API_URL"]),
        bank_id=values["HINDSIGHT_BANK_ID"],
        headers=headers,
        user_tag=user_tag,
    )


def _endpoint(config: RetentionConfig, suffix: str) -> str:
    parts = urlsplit(config.api_base_url)
    base_path = parts.path.rstrip("/")
    bank_id = quote(config.bank_id, safe="")
    path = f"{base_path}/v1/default/banks/{bank_id}/{suffix.lstrip('/')}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def redact_secrets(text: str) -> str:
    text = PRIVATE_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", text)
    text = AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", text)
    text = BEARER_PATTERN.sub(r"\1[REDACTED]", text)

    def redact_assignment(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}"

    text = ASSIGNMENT_PATTERN.sub(redact_assignment, text)
    return TOKEN_PATTERN.sub("[REDACTED TOKEN]", text)


def _text_of(content: Any) -> str:
    """Prose only: `type == "text"` blocks. tool_use / tool_result / thinking blocks are
    intentionally excluded — memory is the conversation, not raw tool traffic."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def parse_transcript(transcript_path: Path) -> tuple[list[str], dict[str, list[Message]]]:
    """Parse Claude Code session JSONL defensively, grouped into turns by `promptId`.

    Only user records carry `promptId`; assistant records attach positionally to the most
    recent user prompt. A turn's submitted content is its user prompt(s) plus the LAST
    non-empty assistant text — intermediate assistant prose between tool calls is progress
    narration, the final record is the answer.
    """
    turn_order: list[str] = []
    prompts: dict[str, list[str]] = {}
    answers: dict[str, list[str]] = {}
    current_turn: str | None = None

    try:
        transcript_file = transcript_path.open("r", encoding="utf-8", errors="replace")
    except OSError as error:
        raise RetentionError("transcript: cannot read Claude Code transcript") from error

    with transcript_file:
        for line in transcript_file:
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                # The transcript format is not a documented contract; tolerate unknown or
                # partial records (including a torn final line mid-write).
                continue
            if not isinstance(record, dict):
                continue
            if record.get("type") not in ("user", "assistant"):
                continue
            if any(record.get(flag) is True for flag in FILTER_FLAGS):
                continue
            if record.get("toolUseResult") is not None:
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            text = _text_of(message.get("content")).strip()

            if record.get("type") == "user" and role == "user":
                prompt_id = record.get("promptId")
                if isinstance(prompt_id, str) and prompt_id:
                    current_turn = prompt_id
                    if prompt_id not in prompts:
                        turn_order.append(prompt_id)
                        prompts[prompt_id] = []
                        answers[prompt_id] = []
                elif current_turn is None:
                    continue
                while True:
                    stripped = IDE_CONTEXT_RE.sub("", text, count=1)
                    if stripped == text:
                        break
                    text = stripped
                text = text.strip()
                if not text or HARNESS_TAG_RE.match(text):
                    continue
                prompts[current_turn].append(redact_secrets(text))
            elif record.get("type") == "assistant" and role == "assistant":
                if current_turn is None or not text:
                    continue
                answers[current_turn].append(redact_secrets(text))

    turns: dict[str, list[Message]] = {}
    for turn_id in turn_order:
        messages = [
            Message(role="user", phase="prompt", text=text) for text in prompts[turn_id]
        ]
        if answers[turn_id]:
            messages.append(
                Message(role="assistant", phase="final_answer", text=answers[turn_id][-1])
            )
        turns[turn_id] = messages
    return turn_order, turns


def format_turn(messages: list[Message]) -> str:
    conversation = [
        {"role": message.role, "content": message.text}
        for message in messages
    ]
    return json.dumps(conversation, ensure_ascii=False, separators=(",", ":"))


def document_id(session_id: str, prompt_id: str) -> str:
    digest = hashlib.sha256(f"{session_id}\0{prompt_id}".encode()).hexdigest()
    return f"claude-turn-{digest}"


def stable_project(cwd: str) -> str:
    """A stable logical project identity: the last two path components of the working
    directory (e.g. `quin7ilian/claude-code`). Physical prefixes (/home, /var/home,
    drive letters) change across machines and OS migrations; entity names fed to the
    memory store must not."""
    parts = [part for part in re.split(r"[/\\]+", cwd) if part]
    return "/".join(parts[-2:]) if parts else ""


def build_item(
    session_id: str,
    prompt_id: str,
    cwd: str,
    messages: list[Message],
    user_tag: str = "",
) -> dict[str, Any]:
    project = stable_project(cwd)
    # Tags travel with the document and with every fact extracted from it, so retrieval
    # can scope by project or source. Keep the vocabulary stable: `key:value`, lowercase.
    tags = [
        "source:claude-code",
        f"project:{project}" if project else "project:unknown",
        f"session:{session_id}",
    ]
    if user_tag:
        tags.insert(0, f"user:{user_tag}")
    return {
        "tags": tags,
        "content": format_turn(messages),
        "context": (
            "Claude Code coding turn encoded as JSON with explicit roles. User entries are "
            "user-authored requests or follow-ups; assistant entries are Claude's final "
            "answers reporting its response, decisions, or outcomes. "
            f"Project: {project}"
        ),
        "metadata": {
            "source": "claude-code",
            "session_id": session_id,
            "prompt_id": prompt_id,
            "project": project,
            "cwd": cwd,
        },
        "document_id": document_id(session_id, prompt_id),
        "update_mode": "replace",
    }


def _safe_failure(error: BaseException) -> RetentionError:
    if isinstance(error, HTTPError):
        return RetentionError(f"http: Hindsight returned status {error.code}")
    if isinstance(error, (TimeoutError, URLError)):
        return RetentionError("network: Hindsight request failed or timed out")
    if isinstance(error, (json.JSONDecodeError, UnicodeDecodeError)):
        return RetentionError("http: Hindsight returned an invalid JSON response")
    if isinstance(error, RetentionError):
        return error
    return RetentionError("internal: retention hook failed")


def default_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    request_headers = dict(headers)
    request_headers["Accept"] = "application/json"
    request_headers["User-Agent"] = USER_AGENT
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    elif method == "POST":
        data = b""

    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with build_opener(NoRedirectHandler).open(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RetentionError(f"http: Hindsight returned status {response.status}")
            decoded = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        raise _safe_failure(error) from error
    if not isinstance(decoded, dict):
        raise RetentionError("http: Hindsight returned an invalid JSON object")
    return decoded


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_state(start_turn_id: str) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "start_turn_id": start_turn_id,
        "completed_turn_ids": [],
        "submitted": {},
        "operations": [],
        "last_attempt_at": None,
        "last_accepted_at": None,
        "last_error": None,
        "last_recovery_error": None,
    }


def _normalize_state(raw_state: Any, start_turn_id: str) -> dict[str, Any]:
    if not isinstance(raw_state, dict) or raw_state.get("version") != STATE_VERSION:
        return _new_state(start_turn_id)
    state = _new_state(start_turn_id)
    stored_start = raw_state.get("start_turn_id")
    if isinstance(stored_start, str) and stored_start:
        state["start_turn_id"] = stored_start
    completed = raw_state.get("completed_turn_ids")
    if isinstance(completed, list):
        state["completed_turn_ids"] = [item for item in completed if isinstance(item, str)]
    submitted = raw_state.get("submitted")
    if isinstance(submitted, dict):
        state["submitted"] = {
            turn_id: content_hash
            for turn_id, content_hash in submitted.items()
            if isinstance(turn_id, str) and isinstance(content_hash, str)
        }
    operations = raw_state.get("operations")
    if isinstance(operations, list):
        state["operations"] = [
            operation
            for operation in operations
            if isinstance(operation, dict)
            and isinstance(operation.get("operation_id"), str)
            and isinstance(operation.get("turn_ids"), list)
            and all(isinstance(turn_id, str) for turn_id in operation["turn_ids"])
        ]
    for key in (
        "last_attempt_at",
        "last_accepted_at",
        "last_error",
        "last_recovery_error",
    ):
        value = raw_state.get(key)
        state[key] = value if isinstance(value, str) or value is None else None
    return state


def _state_file(state_dir: Path, session_id: str) -> Path:
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()
    return state_dir / f"{session_hash}.json"


def _read_state(path: Path, start_turn_id: str) -> dict[str, Any]:
    if not path.is_file():
        return _new_state(start_turn_id)
    try:
        raw_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _new_state(start_turn_id)
    return _normalize_state(raw_state, start_turn_id)


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(state, temporary_file, ensure_ascii=False, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _valid_operation_id(operation_id: str) -> bool:
    try:
        uuid.UUID(operation_id)
    except (ValueError, AttributeError):
        return False
    return True


def _recover_one_operation(
    config: RetentionConfig,
    state: dict[str, Any],
    timeout: float,
    transport: Transport,
) -> None:
    operations = state["operations"]
    if not operations:
        return
    operation = operations.pop(0)
    operation_id = operation["operation_id"]
    if not _valid_operation_id(operation_id):
        state["last_recovery_error"] = "state: discarded invalid operation ID"
        return

    operation_path = f"operations/{quote(operation_id, safe='')}"
    try:
        result = transport(
            "GET", _endpoint(config, operation_path), config.headers, None, timeout
        )
    except RetentionError as error:
        operations.append(operation)
        state["last_recovery_error"] = str(error)
        return

    status = result.get("status")
    if status == "completed":
        completed = set(state["completed_turn_ids"])
        completed.update(operation["turn_ids"])
        state["completed_turn_ids"] = sorted(completed)
        state["last_recovery_error"] = None
        return
    if status == "failed":
        try:
            retried = transport(
                "POST",
                _endpoint(config, f"{operation_path}/retry"),
                config.headers,
                None,
                timeout,
            )
            if retried.get("success") is not True:
                raise RetentionError("recovery: Hindsight rejected operation retry")
            state["last_recovery_error"] = None
        except RetentionError as error:
            state["last_recovery_error"] = str(error)
        operations.append(operation)
        return
    if status in ("cancelled", "not_found"):
        # The documents never landed: drop the submitted hashes so the stable turn
        # documents become eligible for resubmission.
        for turn_id in operation["turn_ids"]:
            state["submitted"].pop(turn_id, None)
        state["last_recovery_error"] = f"recovery: resubmitting {status} operation"
        return

    if status not in ("pending", "processing"):
        state["last_recovery_error"] = "recovery: unknown operation status"
    else:
        state["last_recovery_error"] = None
    operations.append(operation)


def _content_hash(messages: list[Message]) -> str:
    return hashlib.sha256(format_turn(messages).encode()).hexdigest()


def _eligible_turn_ids(
    turn_order: list[str],
    current_turn_id: str,
    turns: dict[str, list[Message]],
    state: dict[str, Any],
) -> list[str]:
    """Turns in the window whose current content has not been submitted yet.

    A turn already submitted with identical content is skipped. A turn whose content has
    since grown (the transcript is flushed asynchronously, so a hook firing can observe a
    truncated turn) is resubmitted — its replace-mode document converges to the full
    content. Turns in a pending operation wait for that operation to resolve first, so
    two in-flight replacements can never race each other.
    """
    start_turn_id = state["start_turn_id"]
    if start_turn_id in turn_order and current_turn_id in turn_order:
        start_index = turn_order.index(start_turn_id)
        end_index = turn_order.index(current_turn_id) + 1
        considered = turn_order[start_index:end_index]
    else:
        considered = [current_turn_id]
    pending: set[str] = set()
    for operation in state["operations"]:
        pending.update(operation["turn_ids"])
    return [
        turn_id
        for turn_id in considered
        if turn_id not in pending
        and turns.get(turn_id)
        and state["submitted"].get(turn_id) != _content_hash(turns[turn_id])
    ]


def _current_turn_id(hook_input: dict[str, Any], turn_order: list[str]) -> str | None:
    """The turn to retain: the Stop hook's `prompt_id`, or (the binary allows it to be
    absent) the transcript's last opened turn."""
    prompt_id = hook_input.get("prompt_id")
    if isinstance(prompt_id, str) and prompt_id:
        return prompt_id
    if turn_order:
        return turn_order[-1]
    return None


def run_hook(
    hook_input: dict[str, Any],
    env_path: Path,
    state_dir: Path,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    transport: Transport = default_transport,
) -> str:
    if hook_input.get("hook_event_name") not in ("Stop", "SessionEnd"):
        return "skipped_event"
    if hook_input.get("stop_hook_active") is True:
        return "skipped_stop_hook_active"
    session_id = hook_input.get("session_id")
    transcript_value = hook_input.get("transcript_path")
    cwd = hook_input.get("cwd")
    if not all(isinstance(value, str) and value for value in (session_id, transcript_value, cwd)):
        return "skipped_input"
    if timeout <= 0:
        return "skipped_timeout"

    try:
        config = load_retention_config(env_path)
        turn_order, turns = parse_transcript(Path(transcript_value))
    except RetentionError:
        return "skipped_configuration_or_transcript"
    current_turn_id = _current_turn_id(hook_input, turn_order)
    if not current_turn_id:
        return "skipped_input"
    if current_turn_id not in turns or not turns[current_turn_id]:
        return "skipped_empty_turn"

    try:
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(state_dir, 0o700)
        lock_path = state_dir / f"{hashlib.sha256(session_id.encode()).hexdigest()}.lock"
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.chmod(lock_path, 0o600)
    except OSError:
        return "skipped_state"

    with os.fdopen(lock_descriptor, "r+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "skipped_locked"

        state_path = _state_file(state_dir, session_id)
        state = _read_state(state_path, current_turn_id)
        try:
            _recover_one_operation(config, state, timeout, transport)
            target_turn_ids = _eligible_turn_ids(turn_order, current_turn_id, turns, state)
            items: list[dict[str, Any]] = []
            submitted_hashes: dict[str, str] = {}
            for turn_id in target_turn_ids:
                messages = turns[turn_id]
                items.append(build_item(session_id, turn_id, cwd, messages, config.user_tag))
                submitted_hashes[turn_id] = _content_hash(messages)

            state["last_attempt_at"] = _now()
            _write_state(state_path, state)
            if not items:
                return "nothing_to_submit"

            result = transport(
                "POST",
                _endpoint(config, "memories"),
                config.headers,
                {"items": items, "async": True},
                timeout,
            )
            operation_id = result.get("operation_id")
            if (
                result.get("success") is not True
                or result.get("async") is not True
                or not isinstance(operation_id, str)
                or not _valid_operation_id(operation_id)
            ):
                raise RetentionError("http: Hindsight did not accept asynchronous retention")
            state["operations"].append(
                {"operation_id": operation_id, "turn_ids": sorted(submitted_hashes)}
            )
            state["submitted"].update(submitted_hashes)
            state["last_accepted_at"] = _now()
            state["last_error"] = None
            _write_state(state_path, state)
            return "accepted"
        except RetentionError as error:
            state["last_error"] = str(error)
            try:
                _write_state(state_path, state)
            except OSError:
                pass
            return "failed"
        except OSError:
            return "failed_state"


def dry_run(hook_input: dict[str, Any]) -> int:
    """Parse the transcript and print what WOULD be retained — no config required, no
    state touched, nothing submitted. For validating the parser against real sessions."""
    transcript_value = hook_input.get("transcript_path")
    if not isinstance(transcript_value, str) or not transcript_value:
        print(json.dumps({"error": "transcript_path missing from hook input"}))
        return 1
    try:
        turn_order, turns = parse_transcript(Path(transcript_value))
    except RetentionError as error:
        print(json.dumps({"error": str(error)}))
        return 1
    current = _current_turn_id(hook_input, turn_order)
    session_id = hook_input.get("session_id") or "session"
    summary = {
        "turn_count": len(turn_order),
        "current_turn_id": current,
        "turns": [
            {
                "prompt_id": turn_id,
                "roles": [message.role for message in turns[turn_id]],
                "content_bytes": len(format_turn(turns[turn_id]).encode("utf-8")),
                "document_id": document_id(str(session_id), turn_id),
            }
            for turn_id in turn_order
        ],
        "current_turn_payload": (
            [
                {"role": message.role, "content": message.text}
                for message in turns[current]
            ]
            if current in turns
            else None
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(hook_input, dict):
        return 0
    if args.dry_run:
        return dry_run(hook_input)
    try:
        run_hook(
            hook_input,
            env_path=args.env_file,
            state_dir=args.state_dir,
            timeout=args.http_timeout,
        )
    except Exception:
        # A lifecycle integration must remain fail-open even after an unforeseen parser
        # or I/O error.
        pass
    # Retention is fail-open: it must never prevent Claude Code from completing the turn.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
