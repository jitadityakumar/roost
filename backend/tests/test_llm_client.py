import json
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


def test_run_claude_prompt_passes_disallowed_tools_when_deny_all(monkeypatch):
    def fake_run(argv, capture_output, text, timeout):
        assert argv == ["claude", "-p", "hello", "--model", "haiku", "--disallowedTools", "*"]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_client.run_claude_prompt("hello", "haiku", 10, disallow_all_tools=True)


def test_run_claude_prompt_passes_output_format_and_schema_when_json_schema_given(monkeypatch):
    schema = {"type": "object", "properties": {"a": {"type": ["integer", "null"]}}}

    def fake_run(argv, capture_output, text, timeout):
        assert argv == [
            "claude",
            "-p",
            "hello",
            "--model",
            "haiku",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
        ]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_client.run_claude_prompt("hello", "haiku", 10, json_schema=schema)


def test_run_claude_prompt_uses_structured_output_allowlist_when_deny_all_and_schema_combined(monkeypatch):
    # This is the exact combination text_extract uses. `--disallowedTools
    # "*"` would also deny the CLI's own internal StructuredOutput tool
    # (confirmed empirically against the real CLI — the model calls
    # StructuredOutput, gets denied twice, then gives up with is_error
    # false but no usable structured_output or parseable result). Must use
    # `--allowedTools StructuredOutput` instead, which still implicitly
    # denies every other tool.
    schema = {"type": "object", "properties": {"a": {"type": ["integer", "null"]}}}

    def fake_run(argv, capture_output, text, timeout):
        assert argv == [
            "claude",
            "-p",
            "hello",
            "--model",
            "haiku",
            "--allowedTools",
            "StructuredOutput",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
        ]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_client.run_claude_prompt("hello", "haiku", 10, json_schema=schema, disallow_all_tools=True)


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


def _envelope(**overrides):
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": '{"a": 1}',
        "total_cost_usd": 0.002,
        "duration_ms": 750,
    }
    base.update(overrides)
    return base


def test_parse_structured_output_prefers_structured_output_field():
    envelope = _envelope(structured_output={"a": 1})
    assert llm_client.parse_structured_output(json.dumps(envelope)) == {"a": 1}


def test_parse_structured_output_falls_back_to_result_field():
    # No structured_output key at all — falls back to tolerantly parsing the
    # (still code-fenced, per the empirical envelope shape) result field.
    envelope = _envelope(result='```json\n{"a": 1}\n```')
    assert llm_client.parse_structured_output(json.dumps(envelope)) == {"a": 1}


def test_parse_structured_output_raises_on_is_error():
    envelope = _envelope(is_error=True, result="the model refused")
    with pytest.raises(llm_client.LlmCallError, match="is_error"):
        llm_client.parse_structured_output(json.dumps(envelope))


def test_parse_structured_output_raises_on_unparseable_envelope():
    with pytest.raises(llm_client.LlmCallError, match="unparseable claude JSON envelope"):
        llm_client.parse_structured_output("not an envelope at all")


def test_parse_structured_output_logs_cost_and_duration(caplog):
    envelope = _envelope(structured_output={"a": 1}, total_cost_usd=0.0042, duration_ms=1234)
    with caplog.at_level("INFO"):
        llm_client.parse_structured_output(json.dumps(envelope))
    assert "0.0042" in caplog.text
    assert "1234" in caplog.text


def test_parse_structured_output_logs_cost_and_duration_even_on_is_error(caplog):
    # A failed call still accrues real cost — the log line must not be
    # skipped just because the call ultimately raises.
    envelope = _envelope(is_error=True, result="refused", total_cost_usd=0.0099, duration_ms=42)
    with caplog.at_level("INFO"):
        with pytest.raises(llm_client.LlmCallError):
            llm_client.parse_structured_output(json.dumps(envelope))
    assert "0.0099" in caplog.text
    assert "42" in caplog.text


def test_parse_structured_output_raises_on_non_dict_envelope():
    with pytest.raises(llm_client.LlmCallError, match="not an object"):
        llm_client.parse_structured_output(json.dumps([1, 2, 3]))


def test_parse_structured_output_falls_back_when_structured_output_not_a_dict():
    # structured_output present but the wrong type (e.g. a list) — treated
    # the same as absent, falling back to parsing the result field.
    envelope = _envelope(structured_output=[1, 2, 3], result='{"a": 1}')
    assert llm_client.parse_structured_output(json.dumps(envelope)) == {"a": 1}


def test_run_claude_prompt_combines_allow_read_and_json_schema(monkeypatch):
    # The actual shape the two vision handlers use — allow_read=True and
    # json_schema together in one call.
    schema = {"type": "object", "properties": {"a": {"type": ["integer", "null"]}}}

    def fake_run(argv, capture_output, text, timeout):
        assert argv == [
            "claude",
            "-p",
            "hello",
            "--model",
            "haiku",
            "--allowedTools",
            "Read",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
        ]
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_client.run_claude_prompt("hello", "haiku", 10, allow_read=True, json_schema=schema)
