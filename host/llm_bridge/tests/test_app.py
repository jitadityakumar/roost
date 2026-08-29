import json
import os

import pytest
from fastapi.testclient import TestClient

from llm_bridge import app as app_module
from llm_bridge.backends.base import BackendError
from llm_bridge.config import ATTACHED_IMAGE_SENTINEL

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_request.json")


class FakeBackend:
    def __init__(self, run_fn=None, available=True):
        self._run_fn = run_fn or (lambda **kwargs: "fake stdout")
        self._available = available
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self._run_fn(**kwargs)

    def available(self):
        return self._available


@pytest.fixture
def client(monkeypatch):
    return TestClient(app_module.app)


@pytest.fixture
def fake_backend(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setitem(app_module._backend_instances, "claude", backend)
    return backend


def _body(**overrides):
    with open(FIXTURE_PATH) as f:
        body = json.load(f)
    body.update(overrides)
    return body


def test_run_llm_success_returns_stdout(client, fake_backend):
    fake_backend._run_fn = lambda **kwargs: '{"a": 1}'
    resp = client.post("/v1/llm/text_extract", json=_body())
    assert resp.status_code == 200
    assert resp.json() == {"stdout": '{"a": 1}'}


def test_run_llm_backend_error_maps_to_error_shape(client, fake_backend):
    def boom(**kwargs):
        raise BackendError("claude exited 1", permanent=False)

    fake_backend._run_fn = boom
    resp = client.post("/v1/llm/text_extract", json=_body())
    assert resp.status_code == 502
    assert resp.json() == {"error": "claude exited 1", "permanent": False}


def test_run_llm_unknown_job_type_returns_permanent_400(client, fake_backend):
    resp = client.post("/v1/llm/not_a_real_job_type", json=_body())
    assert resp.status_code == 400
    body = resp.json()
    assert body["permanent"] is True


def test_run_llm_image_without_sentinel_rejected(client, fake_backend):
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt="no sentinel here", image_base64="aGVsbG8=", image_suffix=".jpg"),
    )
    assert resp.status_code == 400
    assert resp.json()["permanent"] is True


def test_run_llm_sentinel_without_image_rejected(client, fake_backend):
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}"),
    )
    assert resp.status_code == 400
    assert resp.json()["permanent"] is True


def test_run_llm_image_decoded_to_real_temp_file_and_cleaned_up(client, fake_backend):
    # Sentinel substitution itself is ClaudeBackend's job (see
    # test_claude_backend.py) -- the route's own responsibility is just
    # decoding image_base64 to a real temp file and passing its path through
    # as image_path, unchanged prompt, then cleaning up afterwards.
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        assert os.path.exists(kwargs["image_path"])
        assert open(kwargs["image_path"], "rb").read() == b"hello"
        return "ok"

    fake_backend._run_fn = capture
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64="aGVsbG8=", image_suffix=".jpg"),
    )
    assert resp.status_code == 200
    assert seen["prompt"] == f"see {ATTACHED_IMAGE_SENTINEL}"
    assert seen["image_path"].endswith(".jpg")
    assert not os.path.exists(seen["image_path"])  # cleaned up after the request


def test_run_llm_missing_required_field_returns_bridge_error_shape(client, fake_backend):
    body = _body()
    del body["prompt"]
    resp = client.post("/v1/llm/text_extract", json=body)
    assert resp.status_code == 400
    body = resp.json()
    assert set(body.keys()) == {"error", "permanent"}
    assert body["permanent"] is True


def test_healthz_reflects_backend_availability(client, fake_backend):
    fake_backend._available = True
    assert client.get("/healthz").json() == {"ok": True}

    fake_backend._available = False
    resp = client.get("/healthz")
    assert resp.status_code == 503


def test_sentinel_matches_documented_literal_value():
    # No shared import with backend/app/jobs/llm_prompts.py by design -- see
    # config.py's comment. Asserted literally on both sides so a one-sided
    # edit fails its own suite instead of only failing against the real
    # other side.
    assert ATTACHED_IMAGE_SENTINEL == "<<ATTACHED_IMAGE>>"


def test_sample_request_fixture_accepted_as_is(client, fake_backend):
    with open(FIXTURE_PATH) as f:
        body = json.load(f)
    resp = client.post("/v1/llm/text_extract", json=body)
    assert resp.status_code == 200


def test_unknown_route_returns_bridge_error_shape_not_fastapi_default(client, fake_backend):
    # A trailing slash on ROOST_LLM_BRIDGE_BASE (container-side) produces a
    # double-slash request path here -- without a StarletteHTTPException
    # handler, FastAPI's default 404 {"detail": "Not Found"} would leak
    # through, the container's error parser wouldn't find "error"/
    # "permanent" in it, and it would default to permanent=False -- an
    # unreachable-forever misconfiguration retried indefinitely.
    resp = client.get("/not-a-real-route")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"error", "permanent"}
    assert body["permanent"] is True


def test_wrong_method_returns_bridge_error_shape(client, fake_backend):
    resp = client.get("/v1/llm/text_extract")
    assert resp.status_code == 405
    body = resp.json()
    assert set(body.keys()) == {"error", "permanent"}
    assert body["permanent"] is True


def test_run_llm_image_suffix_rejects_path_traversal(client, fake_backend):
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(
            prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64="aGVsbG8=", image_suffix="/../../tmp/evil"
        ),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["permanent"] is True
    assert fake_backend.calls == []


def test_run_llm_image_suffix_rejects_non_extension_values(client, fake_backend):
    for bad_suffix in ["", "jpg", "..jpg", "a" * 20]:
        resp = client.post(
            "/v1/llm/floor_area_vision",
            json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64="aGVsbG8=", image_suffix=bad_suffix),
        )
        assert resp.status_code == 400, bad_suffix
        assert resp.json()["permanent"] is True


def test_run_llm_oversized_image_rejected_before_backend_call(client, fake_backend):
    import base64

    oversized = base64.b64encode(b"x" * (app_module.MAX_IMAGE_BYTES + 1)).decode("ascii")
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64=oversized, image_suffix=".jpg"),
    )
    assert resp.status_code == 400
    assert resp.json()["permanent"] is True
    assert fake_backend.calls == []


def test_run_llm_malformed_base64_rejected(client, fake_backend):
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64="not valid base64!!", image_suffix=".jpg"),
    )
    assert resp.status_code == 400
    assert resp.json()["permanent"] is True
    assert fake_backend.calls == []


def test_run_llm_temp_file_cleaned_up_when_backend_raises(client, fake_backend):
    seen_path = {}

    def boom(**kwargs):
        seen_path["path"] = kwargs["image_path"]
        raise BackendError("claude exited 1", permanent=False)

    fake_backend._run_fn = boom
    resp = client.post(
        "/v1/llm/floor_area_vision",
        json=_body(prompt=f"see {ATTACHED_IMAGE_SENTINEL}", image_base64="aGVsbG8=", image_suffix=".jpg"),
    )
    assert resp.status_code == 502
    assert not os.path.exists(seen_path["path"])


def test_unhandled_exception_returns_bridge_error_shape(fake_backend):
    # raise_server_exceptions=False: the default TestClient re-raises a
    # handler's unhandled exception into the test itself (useful for
    # catching bugs during development) rather than exercising the
    # production behavior this test is actually checking -- that a real
    # deployment's ASGI server gets back a normal {"error","permanent"}
    # response, not a crashed connection.
    no_raise_client = TestClient(app_module.app, raise_server_exceptions=False)

    def boom(**kwargs):
        raise RuntimeError("something genuinely unexpected")

    fake_backend._run_fn = boom
    resp = no_raise_client.post("/v1/llm/text_extract", json=_body())
    assert resp.status_code == 500
    body = resp.json()
    assert set(body.keys()) == {"error", "permanent"}
    assert body["permanent"] is False
