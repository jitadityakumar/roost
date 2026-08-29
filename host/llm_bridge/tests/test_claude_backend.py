import json
import subprocess

import pytest

from llm_bridge.backends.base import BackendError
from llm_bridge.backends.claude_backend import ClaudeBackend


def test_run_passes_allowed_tools_when_allow_read(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        assert argv == ["claude", "-p", "hello", "--model", "haiku", "--allowedTools", "Read"]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeBackend().run("hello", "haiku", 10, allow_read=True, disallow_all_tools=False, json_schema=None, image_path=None)


def test_run_passes_disallowed_tools_when_deny_all(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        assert argv == ["claude", "-p", "hello", "--model", "haiku", "--disallowedTools", "*"]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeBackend().run(
        "hello", "haiku", 10, allow_read=False, disallow_all_tools=True, json_schema=None, image_path=None
    )


def test_run_uses_structured_output_allowlist_when_deny_all_and_schema_combined(monkeypatch):
    schema = {"type": "object", "properties": {"a": {"type": ["integer", "null"]}}}

    def fake_run(argv, capture_output, text, timeout):
        assert argv == [
            "claude", "-p", "hello", "--model", "haiku",
            "--allowedTools", "StructuredOutput",
            "--output-format", "json", "--json-schema", json.dumps(schema),
        ]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeBackend().run(
        "hello", "haiku", 10, allow_read=False, disallow_all_tools=True, json_schema=schema, image_path=None
    )


def test_run_returns_stdout_on_success(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        return subprocess.CompletedProcess(argv, 0, stdout='{"a": 1}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = ClaudeBackend().run(
        "hello", "haiku", 10, allow_read=False, disallow_all_tools=False, json_schema=None, image_path=None
    )
    assert out == '{"a": 1}'


def test_run_raises_on_nonzero_exit(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BackendError, match="boom"):
        ClaudeBackend().run(
            "hello", "haiku", 10, allow_read=False, disallow_all_tools=False, json_schema=None, image_path=None
        )


def test_run_raises_on_timeout(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BackendError, match="timed out"):
        ClaudeBackend().run(
            "hello", "haiku", 10, allow_read=False, disallow_all_tools=False, json_schema=None, image_path=None
        )


def test_run_raises_permanent_error_when_binary_missing(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        raise FileNotFoundError("no such file: claude")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BackendError) as exc_info:
        ClaudeBackend().run(
            "hello", "haiku", 10, allow_read=False, disallow_all_tools=False, json_schema=None, image_path=None
        )
    assert exc_info.value.permanent is True


def test_run_substitutes_sentinel_with_image_path(monkeypatch):
    from llm_bridge.config import ATTACHED_IMAGE_SENTINEL

    seen_argv = []

    def fake_run(argv, capture_output, text, timeout):
        seen_argv.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeBackend().run(
        f"see {ATTACHED_IMAGE_SENTINEL}",
        "haiku",
        10,
        allow_read=True,
        disallow_all_tools=False,
        json_schema=None,
        image_path="/tmp/fake123.jpg",
    )
    prompt_arg = seen_argv[0][2]
    assert prompt_arg == "see /tmp/fake123.jpg"
    assert ATTACHED_IMAGE_SENTINEL not in prompt_arg


def test_available_reflects_which(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert ClaudeBackend().available() is False

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/claude")
    assert ClaudeBackend().available() is True
