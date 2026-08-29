import json
import urllib.error
import urllib.request

import pytest

from app.jobs import llm_client


class _FakeResponse:
    """Minimal stand-in for the context-manager object urllib.request.urlopen
    returns on success."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _envelope_stdout(payload="{}"):
    return payload


@pytest.fixture(autouse=True)
def bridge_base(monkeypatch):
    monkeypatch.setattr(llm_client, "LLM_BRIDGE_BASE", "http://bridge.local:8094")


def test_run_claude_prompt_posts_to_bridge_and_returns_stdout(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps({"stdout": '{"a": 1}'}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)

    assert result == '{"a": 1}'
    assert captured["url"] == "http://bridge.local:8094/v1/llm/text_extract"
    assert captured["timeout"] == 20  # timeout_s + 10s margin
    assert captured["body"] == {
        "prompt": "hello",
        "model": "haiku",
        "timeout_s": 10,
        "allow_read": False,
        "disallow_all_tools": False,
        "json_schema": None,
        "image_base64": None,
        "image_suffix": None,
    }


def test_run_claude_prompt_sends_allow_read_and_disallow_all_tools(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _FakeResponse(json.dumps({"stdout": "{}"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    llm_client.run_claude_prompt("epc_vision", "hello", "haiku", 10, allow_read=True, disallow_all_tools=True)

    assert captured["body"]["allow_read"] is True
    assert captured["body"]["disallow_all_tools"] is True


def test_run_claude_prompt_sends_json_schema(monkeypatch):
    schema = {"type": "object", "properties": {"a": {"type": ["integer", "null"]}}}
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _FakeResponse(json.dumps({"stdout": "{}"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10, json_schema=schema)

    assert captured["body"]["json_schema"] == schema


def test_run_claude_prompt_encodes_image_bytes_and_suffix(monkeypatch):
    import base64

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _FakeResponse(json.dumps({"stdout": "{}"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    llm_client.run_claude_prompt(
        "floor_area_vision",
        "hello <<ATTACHED_IMAGE>>",
        "haiku",
        90,
        allow_read=True,
        image_bytes=b"raw-bytes",
        image_suffix=".jpg",
    )

    assert captured["body"]["image_base64"] == base64.b64encode(b"raw-bytes").decode("ascii")
    assert captured["body"]["image_suffix"] == ".jpg"


def test_run_claude_prompt_raises_permanent_when_bridge_base_unset(monkeypatch):
    monkeypatch.setattr(llm_client, "LLM_BRIDGE_BASE", None)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is True


def test_run_claude_prompt_propagates_permanent_flag_from_http_error_body(monkeypatch):
    def fake_urlopen(req, timeout=None):
        error_body = json.dumps({"error": "unknown job_type", "permanent": True}).encode("utf-8")
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, __import__("io").BytesIO(error_body))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is True
    assert "unknown job_type" in str(exc_info.value)


def test_run_claude_prompt_defaults_permanent_false_on_transient_http_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        error_body = json.dumps({"error": "claude -p exited 1", "permanent": False}).encode("utf-8")
        raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, __import__("io").BytesIO(error_body))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is False


def test_run_claude_prompt_http_error_with_unparseable_body_defaults_permanent_false(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 500, "Internal Server Error", {}, __import__("io").BytesIO(b"not json")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is False


def test_run_claude_prompt_raises_transient_on_url_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is False
    assert "bridge unreachable" in str(exc_info.value)


def test_bridge_available_true_on_200(monkeypatch):
    def fake_urlopen(url, timeout=None):
        return _FakeResponse(json.dumps({"ok": True}).encode("utf-8"), status=200)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert llm_client.bridge_available() is True


def test_bridge_available_false_on_unreachable(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert llm_client.bridge_available() is False


def test_bridge_available_false_on_http_client_exception(monkeypatch):
    # urlopen doesn't wrap every failure in URLError -- something listening
    # on the configured port that isn't actually the bridge (e.g. mid
    # restart, or a stale unrelated process) can raise a raw
    # http.client exception from getresponse() instead. Must not crash the
    # FastAPI lifespan at boot -- same "log loudly, don't raise" contract
    # as any other unreachable-bridge case.
    import http.client

    def fake_urlopen(url, timeout=None):
        raise http.client.RemoteDisconnected("Remote end closed connection")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert llm_client.bridge_available() is False


def test_run_claude_prompt_raises_transient_on_http_client_exception(monkeypatch):
    import http.client

    def fake_urlopen(req, timeout=None):
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError) as exc_info:
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)
    assert exc_info.value.permanent is False


def test_run_claude_prompt_raises_on_non_json_200_body(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(b"not json at all")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError, match="non-JSON"):
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)


def test_run_claude_prompt_raises_on_200_missing_stdout_field(monkeypatch):
    # A 200 is only a contract, not a guarantee -- a bridge version mismatch
    # or bug there could omit "stdout". Must not raise a raw KeyError that
    # bypasses the permanent-flag machinery every other failure path here
    # goes through.
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(json.dumps({"unexpected": "shape"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_client.LlmCallError, match="unexpected response shape"):
        llm_client.run_claude_prompt("text_extract", "hello", "haiku", 10)


def test_bridge_available_false_when_base_unset(monkeypatch):
    monkeypatch.setattr(llm_client, "LLM_BRIDGE_BASE", None)
    assert llm_client.bridge_available() is False


def test_extract_json_block_logs_full_raw_output_on_failure(caplog):
    long_output = "sorry, I can't help: " + ("y" * 600)
    with caplog.at_level("WARNING"):
        with pytest.raises(llm_client.LlmCallError):
            llm_client.extract_json_block(long_output)

    assert long_output in caplog.text


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
    "score,expected_band",
    [
        (100, "A"),
        (92, "A"),
        (91, "B"),
        (81, "B"),
        (80, "C"),
        (69, "C"),
        (68, "D"),
        (55, "D"),
        (54, "E"),
        (39, "E"),
        (38, "F"),
        (21, "F"),
        (20, "G"),
        (1, "G"),
        (0, None),
    ],
)
def test_epc_band_for_score(score, expected_band):
    assert llm_client.epc_band_for_score(score) == expected_band


@pytest.mark.parametrize(
    "value,expected",
    [
        (81, "B (81)"),
        ("81", "B (81)"),
        (73, "C (73)"),
        (None, None),
        ("not a number", None),
        (0, None),  # coerces to 0, which is below the valid EPC range
    ],
)
def test_epc_rating_from_score(value, expected):
    # Real 2026-08-08 finding: Haiku correctly read a score of 81 off a
    # real EPC graphic but misclassified it as band A instead of B — the
    # app now calculates the band from the score instead of trusting the
    # model's letter.
    assert llm_client.epc_rating_from_score(value) == expected


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
