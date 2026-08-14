import datetime as dt
import io
from urllib.error import HTTPError

import pytest

from app.destinations import client


def test_fetch_journeys_raises_clearly_when_base_unset(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", None)
    with pytest.raises(client.TrainPlannerApiError, match="ROOST_TRAIN_PLANNER_BASE"):
        client.fetch_journeys("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30))


def test_results_url_none_when_base_unset(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", None)
    assert client.results_url("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30)) is None


def test_results_url_builds_expected_query(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")
    url = client.results_url("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30))
    assert url == (
        "http://planner.example/results?from_=WOK&to=PAD&date=2026-08-17"
        "&time=08%3A30&window_minutes=60"
    )


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_journeys_retries_on_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")
    monkeypatch.setattr(client.time, "sleep", lambda *_: None)

    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise HTTPError(url, 503, "busy", {"Retry-After": "2"}, io.BytesIO(b""))
        return _FakeResponse(b'{"journeys": []}')

    monkeypatch.setattr(client, "urlopen", fake_urlopen)

    result = client.fetch_journeys("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30))
    assert result == {"journeys": []}
    assert len(calls) == 2


def test_fetch_journeys_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")
    monkeypatch.setattr(client.time, "sleep", lambda *_: None)

    def fake_urlopen(url, timeout):
        raise HTTPError(url, 503, "busy", {"Retry-After": "2"}, io.BytesIO(b""))

    monkeypatch.setattr(client, "urlopen", fake_urlopen)

    with pytest.raises(client.TrainPlannerApiError):
        client.fetch_journeys("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30))


def test_fetch_journeys_does_not_retry_non_503_errors(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")

    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        raise HTTPError(url, 400, "bad request", {}, io.BytesIO(b""))

    monkeypatch.setattr(client, "urlopen", fake_urlopen)

    with pytest.raises(client.TrainPlannerApiError):
        client.fetch_journeys("WOK", "PAD", dt.date(2026, 8, 17), dt.time(8, 30))
    assert len(calls) == 1


# --- fetch_multi_change_journeys (train-journey-planner issue #26) ---------

def test_fetch_multi_change_journeys_raises_clearly_when_base_unset(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", None)
    with pytest.raises(client.TrainPlannerApiError, match="ROOST_TRAIN_PLANNER_BASE"):
        client.fetch_multi_change_journeys("BNS", "PUL", dt.date(2026, 8, 17), dt.time(8, 30))


def test_fetch_multi_change_journeys_hits_the_multi_change_path(monkeypatch):
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")

    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        return _FakeResponse(b'{"journeys": [], "sidecar_healthy": true}')

    monkeypatch.setattr(client, "urlopen", fake_urlopen)

    result = client.fetch_multi_change_journeys("BNS", "PUL", dt.date(2026, 8, 17), dt.time(8, 30))
    assert result == {"journeys": [], "sidecar_healthy": True}
    assert len(calls) == 1
    assert calls[0].startswith("http://planner.example/api/journeys/multi-change?")


def test_fetch_multi_change_journeys_does_not_retry_on_503(monkeypatch):
    """Unlike fetch_journeys, this endpoint is documented as never 503ing
    (excluded from train-journey-planner's DB concurrency gate) -- confirm
    there's no retry loop here: a 503 (however unexpected) just raises
    immediately rather than sleeping/retrying."""
    monkeypatch.setattr(client, "TRAIN_PLANNER_BASE", "http://planner.example")

    calls = []

    def fake_urlopen(url, timeout):
        calls.append(url)
        raise HTTPError(url, 503, "busy", {"Retry-After": "2"}, io.BytesIO(b""))

    monkeypatch.setattr(client, "urlopen", fake_urlopen)

    with pytest.raises(client.TrainPlannerApiError):
        client.fetch_multi_change_journeys("BNS", "PUL", dt.date(2026, 8, 17), dt.time(8, 30))
    assert len(calls) == 1
