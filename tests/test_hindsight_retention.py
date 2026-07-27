from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from retain_hindsight import (  # noqa: E402
    RetentionError,
    default_transport,
    document_id,
    load_retention_config,
    parse_env_file,
    parse_transcript,
    redact_secrets,
    run_hook,
    stable_project,
)


def user_record(text, prompt_id: str | None = None, **extra) -> dict:
    record = {"type": "user", "message": {"role": "user", "content": text}}
    if prompt_id is not None:
        record["promptId"] = prompt_id
    record.update(extra)
    return record


def assistant_record(*blocks, **extra) -> dict:
    content = [
        block if isinstance(block, dict) else {"type": "text", "text": block}
        for block in blocks
    ]
    record = {"type": "assistant", "message": {"role": "assistant", "content": content}}
    record.update(extra)
    return record


def write_transcript(path: Path, records: list[dict], malformed_tail: bool = False) -> None:
    rendered = "".join(json.dumps(record) + "\n" for record in records)
    if malformed_tail:
        rendered += '{"partial":'
    path.write_text(rendered, encoding="utf-8")


def stored_env(path: Path) -> None:
    path.write_text(
        '''
# Hindsight connection
export HINDSIGHT_API_URL="https://hindsight.example/prefix"
HINDSIGHT_API_KEY=test-value  # inline comment
HINDSIGHT_BANK_ID='main bank'
''',
        encoding="utf-8",
    )


def stop_input(transcript: Path, prompt_id: str | None, cwd: str = "/workspace") -> dict:
    hook_input = {
        "hook_event_name": "Stop",
        "session_id": "session",
        "transcript_path": str(transcript),
        "cwd": cwd,
    }
    if prompt_id is not None:
        hook_input["prompt_id"] = prompt_id
    return hook_input


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.responses: list[dict | BaseException] = []

    def queue(self, *responses: dict | BaseException) -> None:
        self.responses.extend(responses)

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict | None,
        timeout: float,
    ) -> dict:
        self.calls.append((method, url, body))
        if not self.responses:
            raise AssertionError("no fake response queued")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class ConfigurationTests(unittest.TestCase):
    def test_parses_env_file_quotes_comments_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                '''
# comment line
export HINDSIGHT_API_URL="https://example.test/mcp"
HINDSIGHT_API_KEY='has#hash'  # trailing note
HINDSIGHT_BANK_ID=main # inline
EMPTY=   # only a comment
''',
                encoding="utf-8",
            )
            values = parse_env_file(env_path)
            self.assertEqual(values["HINDSIGHT_API_URL"], "https://example.test/mcp")
            self.assertEqual(values["HINDSIGHT_API_KEY"], "has#hash")
            self.assertEqual(values["HINDSIGHT_BANK_ID"], "main")
            self.assertEqual(values["EMPTY"], "")

    def test_loads_configuration_and_strips_mcp_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                'HINDSIGHT_API_URL=https://example.test/prefix/mcp\n'
                'HINDSIGHT_API_KEY=token\n'
                'HINDSIGHT_BANK_ID=main bank\n',
                encoding="utf-8",
            )
            configured = load_retention_config(env_path)
            self.assertEqual(configured.api_base_url, "https://example.test/prefix")
            self.assertEqual(configured.bank_id, "main bank")
            self.assertEqual(configured.headers["Authorization"], "Bearer token")
            self.assertEqual(configured.headers["X-Bank-Id"], "main bank")

    def test_optional_user_tag_is_loaded_and_prefixes_item_tags(self) -> None:
        from retain_hindsight import Message, build_item  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            stored_env(env_path)
            with patch.dict(os.environ, {"HINDSIGHT_USER_TAG": ""}, clear=False):
                self.assertEqual(load_retention_config(env_path).user_tag, "")

            env_path.write_text(
                'HINDSIGHT_API_URL=https://example.test\n'
                'HINDSIGHT_API_KEY=token\n'
                'HINDSIGHT_BANK_ID=main\n'
                'HINDSIGHT_USER_TAG=example-user\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HINDSIGHT_USER_TAG", None)
                configured = load_retention_config(env_path)
            self.assertEqual(configured.user_tag, "example-user")

        item = build_item(
            "s1", "p1", "/a/b", [Message("user", "prompt", "hi")], user_tag="example-user"
        )
        self.assertEqual(item["tags"][0], "user:example-user")
        self.assertIn("project:a/b", item["tags"])

    def test_process_environment_wins_over_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            stored_env(env_path)
            with patch.dict(
                os.environ, {"HINDSIGHT_BANK_ID": "override-bank"}, clear=False
            ):
                configured = load_retention_config(env_path)
            self.assertEqual(configured.bank_id, "override-bank")

    def test_missing_keys_and_bad_urls_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text("HINDSIGHT_API_KEY=x\n", encoding="utf-8")
            environment = {key: "" for key in ("HINDSIGHT_API_URL", "HINDSIGHT_BANK_ID")}
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaises(RetentionError):
                    load_retention_config(env_path)
                env_path.write_text(
                    'HINDSIGHT_API_URL=file:///tmp/mcp\n'
                    'HINDSIGHT_API_KEY=x\n'
                    'HINDSIGHT_BANK_ID=main\n',
                    encoding="utf-8",
                )
                with self.assertRaises(RetentionError):
                    load_retention_config(env_path)


class TransportTests(unittest.TestCase):
    def test_standard_library_transport_posts_json_with_authentication(self) -> None:
        captured: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                content_length = int(self.headers.get("Content-Length", "0"))
                captured["path"] = self.path
                captured["authorization"] = self.headers.get("Authorization")
                captured["body"] = json.loads(self.rfile.read(content_length))
                response = json.dumps(
                    {
                        "success": True,
                        "async": True,
                        "operation_id": str(uuid.uuid4()),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format: str, *args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            result = default_transport(
                "POST",
                f"http://127.0.0.1:{server.server_port}/memories",
                {"Authorization": "Bearer local-test"},
                {"items": [{"content": "hello"}], "async": True},
                1.0,
            )
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=1)

        self.assertTrue(result["success"])
        self.assertEqual(captured["path"], "/memories")
        self.assertEqual(captured["authorization"], "Bearer local-test")
        self.assertTrue(captured["body"]["async"])


class TranscriptTests(unittest.TestCase):
    def test_keeps_user_prose_and_last_assistant_text_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "transcript.jsonl"
            records = [
                user_record("meta injection", prompt_id="p1", isMeta=True),
                user_record("Please use api_key=super-secret-value", prompt_id="p1"),
                assistant_record(
                    "Looking into it",
                    {"type": "thinking", "thinking": "hidden reasoning"},
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                ),
                user_record(
                    [{"type": "tool_result", "tool_use_id": "t1", "content": "tool secret"}],
                    prompt_id="p1",
                    toolUseResult={"stdout": "tool secret"},
                ),
                assistant_record("Intermediate progress note"),
                assistant_record("Done: the final answer"),
            ]
            write_transcript(transcript, records, malformed_tail=True)

            order, turns = parse_transcript(transcript)

            self.assertEqual(order, ["p1"])
            parsed = turns["p1"]
            self.assertEqual(
                [(message.role, message.phase) for message in parsed],
                [("user", "prompt"), ("assistant", "final_answer")],
            )
            combined = "\n".join(message.text for message in parsed)
            self.assertIn("api_key=[REDACTED]", combined)
            self.assertIn("Done: the final answer", combined)
            self.assertNotIn("meta injection", combined)
            self.assertNotIn("Looking into it", combined)
            self.assertNotIn("Intermediate progress note", combined)
            self.assertNotIn("hidden reasoning", combined)
            self.assertNotIn("tool secret", combined)

    def test_assistant_records_attach_positionally_to_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "transcript.jsonl"
            write_transcript(
                transcript,
                [
                    user_record("First question", prompt_id="p1"),
                    assistant_record("First answer"),
                    user_record("Second question", prompt_id="p2"),
                    assistant_record("Second answer"),
                ],
            )
            order, turns = parse_transcript(transcript)
            self.assertEqual(order, ["p1", "p2"])
            self.assertEqual(turns["p1"][-1].text, "First answer")
            self.assertEqual(turns["p2"][-1].text, "Second answer")

    def test_filters_flags_harness_tags_and_sentinels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "transcript.jsonl"
            write_transcript(
                transcript,
                [
                    user_record("sidechain", prompt_id="s1", isSidechain=True),
                    user_record("compact summary", prompt_id="s2", isCompactSummary=True),
                    user_record("api error", prompt_id="s3", isApiErrorMessage=True),
                    user_record("hidden", prompt_id="s4", isVisibleInTranscriptOnly=True),
                    user_record("<command-name>/foo</command-name>", prompt_id="p1"),
                    user_record("<local-command-stdout>out</local-command-stdout>", prompt_id="p1"),
                    user_record("<<loop-sentinel>>", prompt_id="p1"),
                    user_record(
                        "<task-notification>\n<task-id>x</task-id>\n</task-notification>",
                        prompt_id="p1",
                    ),
                    user_record(
                        "[SYSTEM NOTIFICATION - NOT USER INPUT]\nautomated event",
                        prompt_id="p1",
                    ),
                    user_record("<<draft>> keep this real prose", prompt_id="p1"),
                    user_record("<div>also real prose</div>", prompt_id="p1"),
                    assistant_record("Answer"),
                ],
            )
            order, turns = parse_transcript(transcript)
            self.assertEqual(order, ["p1"])
            texts = [message.text for message in turns["p1"]]
            self.assertEqual(
                texts,
                ["<<draft>> keep this real prose", "<div>also real prose</div>", "Answer"],
            )

    def test_ide_context_blocks_are_stripped_from_user_prose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "transcript.jsonl"
            write_transcript(
                transcript,
                [
                    user_record(
                        "<ide_opened_file>The user opened /x/y.py in the IDE."
                        "</ide_opened_file><ide_selection>lines 4-5 selected"
                        "</ide_selection>Fix the tiering system please",
                        prompt_id="p1",
                    ),
                    user_record(
                        "<ide_opened_file>only ide context</ide_opened_file>",
                        prompt_id="p2",
                    ),
                    assistant_record("Answer"),
                ],
            )
            order, turns = parse_transcript(transcript)
            self.assertEqual(order, ["p1", "p2"])
            self.assertEqual(
                [message.text for message in turns["p1"]],
                ["Fix the tiering system please"],
            )
            self.assertEqual(
                [(message.role, message.text) for message in turns["p2"]],
                [("assistant", "Answer")],
            )

    def test_command_echo_still_opens_turn_for_its_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            transcript = Path(temporary_directory) / "transcript.jsonl"
            write_transcript(
                transcript,
                [
                    user_record("<command-name>/deploy</command-name>", prompt_id="p1"),
                    assistant_record("Deployed the service"),
                ],
            )
            order, turns = parse_transcript(transcript)
            self.assertEqual(order, ["p1"])
            self.assertEqual(
                [(message.role, message.text) for message in turns["p1"]],
                [("assistant", "Deployed the service")],
            )


class RedactionTests(unittest.TestCase):
    def test_redacts_common_bearer_tokens_and_private_keys(self) -> None:
        source = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
            "token Bearer zyxwvutsrqponmlkjihgfedcba\n"
            "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
        )
        redacted = redact_secrets(source)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("zyxwvutsrqponmlkjihgfedcba", redacted)
        self.assertNotIn("\nsecret\n", redacted)


class RunHookTests(unittest.TestCase):
    def test_progress_only_turn_is_skipped_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            stored_env(env_path)
            write_transcript(
                transcript,
                [user_record("<command-name>/status</command-name>", prompt_id="p1")],
            )
            transport = FakeTransport()

            result = run_hook(
                stop_input(transcript, "p1"), env_path, root / "state", transport=transport
            )

            self.assertEqual(result, "skipped_empty_turn")
            self.assertEqual(transport.calls, [])

    def test_user_only_turn_retains_structured_user_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            stored_env(env_path)
            write_transcript(transcript, [user_record("Keep the request", prompt_id="p1")])
            transport = FakeTransport()
            transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )

            result = run_hook(
                stop_input(transcript, "p1"), env_path, root / "state", transport=transport
            )

            self.assertEqual(result, "accepted")
            item = transport.calls[0][2]["items"][0]
            self.assertEqual(
                json.loads(item["content"]),
                [{"role": "user", "content": "Keep the request"}],
            )

    def test_first_stop_retains_only_current_turn_and_records_no_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            write_transcript(
                transcript,
                [
                    user_record("Old prompt", prompt_id="old-turn"),
                    assistant_record("Old answer"),
                    user_record("Current prompt", prompt_id="current-turn"),
                    assistant_record("Current answer"),
                ],
            )
            transport = FakeTransport()
            transport.queue(
                {
                    "success": True,
                    "async": True,
                    "operation_id": str(uuid.uuid4()),
                    "items_count": 1,
                }
            )

            result = run_hook(
                stop_input(transcript, "current-turn", cwd="/workspace/project"),
                env_path,
                state_dir,
                transport=transport,
            )

            self.assertEqual(result, "accepted")
            self.assertEqual(len(transport.calls), 1)
            method, url, body = transport.calls[0]
            self.assertEqual(method, "POST")
            self.assertEqual(
                url,
                "https://hindsight.example/prefix/v1/default/banks/main%20bank/memories",
            )
            self.assertTrue(body["async"])
            self.assertEqual(len(body["items"]), 1)
            item = body["items"][0]
            self.assertEqual(
                json.loads(item["content"]),
                [
                    {"role": "user", "content": "Current prompt"},
                    {"role": "assistant", "content": "Current answer"},
                ],
            )
            self.assertEqual(item["update_mode"], "replace")
            self.assertEqual(item["document_id"], document_id("session", "current-turn"))
            self.assertIn("Claude Code coding turn encoded as JSON", item["context"])
            self.assertIn("Project: workspace/project", item["context"])
            self.assertNotIn("/workspace/project", item["context"])
            self.assertEqual(item["metadata"]["source"], "claude-code")
            self.assertEqual(item["metadata"]["project"], "workspace/project")
            self.assertEqual(item["metadata"]["cwd"], "/workspace/project")
            self.assertEqual(
                item["tags"],
                [
                    "source:claude-code",
                    "project:workspace/project",
                    "session:session",
                ],
            )

            state_files = list(state_dir.glob("*.json"))
            self.assertEqual(len(state_files), 1)
            state_text = state_files[0].read_text(encoding="utf-8")
            self.assertNotIn("Current prompt", state_text)
            self.assertNotIn("test-value", state_text)
            self.assertEqual(state_files[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(state_dir.stat().st_mode & 0o777, 0o700)

    def test_missing_prompt_id_falls_back_to_last_transcript_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            stored_env(env_path)
            write_transcript(
                transcript,
                [
                    user_record("Earlier", prompt_id="p1"),
                    assistant_record("Earlier answer"),
                    user_record("Latest", prompt_id="p2"),
                    assistant_record("Latest answer"),
                ],
            )
            transport = FakeTransport()
            transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )

            result = run_hook(
                stop_input(transcript, None), env_path, root / "state", transport=transport
            )

            self.assertEqual(result, "accepted")
            item = transport.calls[0][2]["items"][0]
            self.assertEqual(item["document_id"], document_id("session", "p2"))
            self.assertIn("Latest", item["content"])
            self.assertNotIn("Earlier", item["content"])

    def test_completed_operation_is_confirmed_then_next_turn_is_submitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            records = [
                user_record("One", prompt_id="turn-1"),
                assistant_record("Answer one"),
            ]
            write_transcript(transcript, records)
            first_transport = FakeTransport()
            first_transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn-1"),
                    env_path,
                    state_dir,
                    transport=first_transport,
                ),
                "accepted",
            )

            records.extend(
                [user_record("Two", prompt_id="turn-2"), assistant_record("Answer two")]
            )
            write_transcript(transcript, records)
            second_transport = FakeTransport()
            second_transport.queue(
                {"status": "completed"},
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())},
            )

            result = run_hook(
                stop_input(transcript, "turn-2"),
                env_path,
                state_dir,
                transport=second_transport,
            )

            self.assertEqual(result, "accepted")
            self.assertEqual([call[0] for call in second_transport.calls], ["GET", "POST"])
            submitted = second_transport.calls[1][2]["items"]
            self.assertEqual(len(submitted), 1)
            self.assertIn("Two", submitted[0]["content"])
            self.assertNotIn("One", submitted[0]["content"])

    def test_failed_request_is_retried_with_the_same_stable_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            write_transcript(
                transcript,
                [user_record("Retry me", prompt_id="turn"), assistant_record("Retry answer")],
            )
            failed_transport = FakeTransport()
            failed_transport.queue(
                RetentionError("network: Hindsight request failed or timed out")
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=failed_transport,
                ),
                "failed",
            )

            accepted_transport = FakeTransport()
            accepted_transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=accepted_transport,
                ),
                "accepted",
            )
            first_document = failed_transport.calls[0][2]["items"][0]["document_id"]
            second_document = accepted_transport.calls[0][2]["items"][0]["document_id"]
            self.assertEqual(first_document, second_document)

    def test_failed_async_operation_is_requeued_before_the_next_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            first_records = [
                user_record("One", prompt_id="turn-1"),
                assistant_record("Answer one"),
            ]
            write_transcript(transcript, first_records)
            first_operation = str(uuid.uuid4())
            initial_transport = FakeTransport()
            initial_transport.queue(
                {"success": True, "async": True, "operation_id": first_operation}
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn-1"),
                    env_path,
                    state_dir,
                    transport=initial_transport,
                ),
                "accepted",
            )

            write_transcript(
                transcript,
                first_records
                + [user_record("Two", prompt_id="turn-2"), assistant_record("Answer two")],
            )
            recovery_transport = FakeTransport()
            recovery_transport.queue(
                {"status": "failed"},
                {"success": True, "operation_id": first_operation},
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())},
            )

            result = run_hook(
                stop_input(transcript, "turn-2"),
                env_path,
                state_dir,
                transport=recovery_transport,
            )

            self.assertEqual(result, "accepted")
            self.assertEqual(
                [call[0] for call in recovery_transport.calls],
                ["GET", "POST", "POST"],
            )
            self.assertTrue(recovery_transport.calls[1][1].endswith(f"/{first_operation}/retry"))
            self.assertTrue(recovery_transport.calls[2][1].endswith("/memories"))

    def test_truncated_turn_is_resubmitted_once_its_content_grows(self) -> None:
        # The transcript is flushed asynchronously: a Stop firing can observe a turn
        # before its final answer record lands on disk. The truncated submission must be
        # replaced by a full one on a later firing.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            records = [
                user_record("Fix the service", prompt_id="turn"),
                assistant_record("Let me syntax-check the change."),
            ]
            write_transcript(transcript, records)
            first_transport = FakeTransport()
            first_transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=first_transport,
                ),
                "accepted",
            )

            # The tail flushes after the first firing.
            records.append(assistant_record("Fixed. Here is the full solution."))
            write_transcript(transcript, records)

            # Same content while the operation is pending: wait, do not race a second
            # replacement against the in-flight one.
            pending_transport = FakeTransport()
            pending_transport.queue({"status": "pending"})
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=pending_transport,
                ),
                "nothing_to_submit",
            )

            # Once the operation resolves, the grown turn is resubmitted in full.
            healing_transport = FakeTransport()
            healing_transport.queue(
                {"status": "completed"},
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())},
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=healing_transport,
                ),
                "accepted",
            )
            item = healing_transport.calls[1][2]["items"][0]
            self.assertEqual(item["document_id"], document_id("session", "turn"))
            self.assertIn("Fixed. Here is the full solution.", item["content"])
            self.assertNotIn("syntax-check", item["content"])

            # Stable content is not submitted again.
            stable_transport = FakeTransport()
            stable_transport.queue({"status": "completed"})
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=stable_transport,
                ),
                "nothing_to_submit",
            )

    def test_cancelled_operation_makes_its_turns_eligible_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            state_dir = root / "state"
            stored_env(env_path)
            write_transcript(
                transcript,
                [user_record("Keep me", prompt_id="turn"), assistant_record("Answer")],
            )
            first_transport = FakeTransport()
            first_transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=first_transport,
                ),
                "accepted",
            )

            recovery_transport = FakeTransport()
            recovery_transport.queue(
                {"status": "cancelled"},
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())},
            )
            self.assertEqual(
                run_hook(
                    stop_input(transcript, "turn"),
                    env_path,
                    state_dir,
                    transport=recovery_transport,
                ),
                "accepted",
            )
            self.assertIn("Keep me", recovery_transport.calls[1][2]["items"][0]["content"])

    def test_session_end_event_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            env_path = root / ".env"
            transcript = root / "transcript.jsonl"
            stored_env(env_path)
            write_transcript(
                transcript,
                [user_record("Final turn", prompt_id="p1"), assistant_record("Answer")],
            )
            transport = FakeTransport()
            transport.queue(
                {"success": True, "async": True, "operation_id": str(uuid.uuid4())}
            )
            hook_input = stop_input(transcript, None)
            hook_input["hook_event_name"] = "SessionEnd"

            result = run_hook(hook_input, env_path, root / "state", transport=transport)

            self.assertEqual(result, "accepted")
            self.assertEqual(
                transport.calls[0][2]["items"][0]["document_id"],
                document_id("session", "p1"),
            )

    def test_non_stop_incomplete_and_reentrant_inputs_fail_open(self) -> None:
        transport = FakeTransport()
        self.assertEqual(
            run_hook({}, Path("missing"), Path("state"), transport=transport),
            "skipped_event",
        )
        self.assertEqual(
            run_hook(
                {"hook_event_name": "Stop"},
                Path("missing"),
                Path("state"),
                transport=transport,
            ),
            "skipped_input",
        )
        self.assertEqual(
            run_hook(
                {"hook_event_name": "Stop", "stop_hook_active": True},
                Path("missing"),
                Path("state"),
                transport=transport,
            ),
            "skipped_stop_hook_active",
        )
        self.assertEqual(transport.calls, [])

    def test_document_ids_are_stable_per_session_and_distinct_across_sessions(self) -> None:
        self.assertEqual(document_id("s1", "p1"), document_id("s1", "p1"))
        self.assertNotEqual(document_id("s1", "p1"), document_id("s2", "p1"))
        self.assertNotEqual(document_id("s1", "p1"), document_id("s1", "p2"))

    def test_stable_project_is_prefix_independent(self) -> None:
        self.assertEqual(stable_project("/home/user/Work/src/org/repo"), "org/repo")
        self.assertEqual(stable_project("/var/home/user/Work/src/org/repo/"), "org/repo")
        self.assertEqual(stable_project("D:\\Work\\src\\org\\repo"), "org/repo")
        self.assertEqual(
            stable_project("/home/user/Work/src/org/repo"),
            stable_project("D:\\Work\\src\\org\\repo"),
        )
        self.assertEqual(stable_project("/tmp"), "tmp")
        self.assertEqual(stable_project("/"), "")


if __name__ == "__main__":
    unittest.main()
