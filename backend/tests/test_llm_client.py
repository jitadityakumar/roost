import subprocess

import pytest

from app.jobs import llm_client


def test_run_claude_prompt_returns_stdout_on_success(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        assert argv == ["claude", "-p", "hello", "--model", "haiku"]
        return subprocess.CompletedProcess(argv, 0, stdout='{"a": 1}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert llm_client.run_claude_prompt("hello", "haiku", 10) == '{"a": 1}'


def test_run_claude_prompt_passes_allowed_tools_when_allow_read(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        assert argv == ["claude", "-p", "hello", "--model", "haiku", "--allowedTools", "Read"]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_client.run_claude_prompt("hello", "haiku", 10, allow_read=True)


def test_run_claude_prompt_raises_on_nonzero_exit(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(llm_client.LlmCallError, match="boom"):
        llm_client.run_claude_prompt("hello", "haiku", 10)


def test_run_claude_prompt_logs_full_stderr_on_nonzero_exit(monkeypatch, caplog):
    # The DB-facing error message is truncated to 500 chars; the whole point
    # of also logging is that a real failure (e.g. an auth error from the
    # mounted ~/.claude session) needs to be diagnosable from `docker logs`
    # without needing to reproduce it interactively.
    long_stderr = "auth error: " + ("x" * 600)

    def fake_run(argv, capture_output, text, timeout):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr=long_stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with caplog.at_level("WARNING"):
        with pytest.raises(llm_client.LlmCallError):
            llm_client.run_claude_prompt("hello", "haiku", 10)

    assert long_stderr in caplog.text


def test_extract_json_block_logs_full_raw_output_on_failure(caplog):
    long_output = "sorry, I can't help: " + ("y" * 600)
    with caplog.at_level("WARNING"):
        with pytest.raises(llm_client.LlmCallError):
            llm_client.extract_json_block(long_output)

    assert long_output in caplog.text


def test_cli_available_reflects_path(monkeypatch):
    monkeypatch.setattr(llm_client.shutil, "which", lambda name: None)
    assert llm_client.cli_available() is False

    monkeypatch.setattr(llm_client.shutil, "which", lambda name: "/usr/local/bin/claude")
    assert llm_client.cli_available() is True


def test_run_claude_prompt_raises_on_timeout(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(llm_client.LlmCallError, match="timed out"):
        llm_client.run_claude_prompt("hello", "haiku", 10)


def test_run_claude_prompt_raises_permanent_error_when_cli_missing(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        raise FileNotFoundError("no such file: claude")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("hello", "haiku", 10)
    assert exc_info.value.permanent is True


def test_extract_json_block_parses_bare_object():
    assert llm_client.extract_json_block('{"a": 1}') == {"a": 1}


def test_extract_json_block_parses_fenced_json():
    raw = '```json\n{"a": 1}\n```'
    assert llm_client.extract_json_block(raw) == {"a": 1}


def test_extract_json_block_parses_object_with_stray_prose():
    raw = 'Sure, here you go:\n{"a": 1}\nHope that helps!'
    assert llm_client.extract_json_block(raw) == {"a": 1}


def test_extract_json_block_raises_on_unparseable_output():
    with pytest.raises(llm_client.LlmCallError, match="no parseable JSON"):
        llm_client.extract_json_block("I couldn't read that image, sorry.")


@pytest.mark.parametrize(
    "value,expected",
    [
        (42, 42),
        (42.6, 43),
        ("1,200", 1200),
        ("£1,200", 1200),
        ("£1,200 p.a.", 1200),
        ("approx. 1,250 sq ft", 1250),
        ("c.1200", 1200),
        ("not a number", None),
        (True, None),
    ],
)
def test_as_int(value, expected):
    assert llm_client.as_int(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(True, True), (False, False), ("true", True), ("False", False), ("no", None), (1, None), (None, None)],
)
def test_as_bool_rejects_truthy_strings(value, expected):
    # "no" must not silently coerce to True via a bare bool(value) call.
    assert llm_client.as_bool(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("D", "D"), ("d", "D"), ("TBC", None), ("Band C", None), ("", None), (None, None)],
)
def test_as_council_tax_band(value, expected):
    assert llm_client.as_council_tax_band(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("C (73)", "C (73)"),
        ("c (73)", "C (73)"),
        ("C", "C"),
        ({"letter": "C", "score": 73}, "C (73)"),
        (None, None),
        ("not legible", None),
    ],
)
def test_as_epc_rating(value, expected):
    assert llm_client.as_epc_rating(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (85, 85.0),
        ("85 sqm", 85.0),
        ("1,250 sq ft", 1250.0),
        ("approx. 85.5 sq m", 85.5),
        (None, None),
    ],
)
def test_as_float(value, expected):
    assert llm_client.as_float(value) == expected


def test_extract_json_block_rejects_non_dict_json():
    with pytest.raises(llm_client.LlmCallError, match="no parseable JSON"):
        llm_client.extract_json_block("null")
    with pytest.raises(llm_client.LlmCallError, match="no parseable JSON"):
        llm_client.extract_json_block("[1, 2]")
