import datetime as dt
import json

import pytest

from app.commute import tfl_client


@pytest.fixture(autouse=True)
def _tfl_key(monkeypatch):
    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def _leg(mode_id, dep_name, dep_id, arr_name, arr_id, duration=5, operator=None):
    leg = {
        "mode": {"id": mode_id},
        "duration": duration,
        "departurePoint": {"commonName": dep_name, "id": dep_id},
        "arrivalPoint": {"commonName": arr_name, "id": arr_id},
    }
    if operator:
        leg["routeOptions"] = [{"name": operator}]
    return leg


def _journey(duration, legs, start="2026-08-17T08:40:00", arrival="2026-08-17T09:04:00"):
    return {"duration": duration, "startDateTime": start, "arrivalDateTime": arrival, "legs": legs}


# --- find_frequent_destination_journey --------------------------------------

def test_returns_none_for_empty_identifier():
    assert tfl_client.find_frequent_destination_journey(51.3, -0.5, "", dt.date(2026, 8, 17), dt.time(8, 30)) is None


def test_direct_journey_with_access_walk_excludes_it_from_changes(monkeypatch):
    legs = [
        _leg("walking", "origin", None, "Woking Rail Station", "910GWOKING", duration=6),
        _leg("national-rail", "Woking Rail Station", "910GWOKING", "London Waterloo", "910GWATRLMN", duration=24, operator="South Western Railway"),
    ]
    payload = {"journeys": [_journey(24, legs)]}
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GWATRLMN", dt.date(2026, 8, 17), dt.time(8, 30)
    )

    assert result["duration_minutes"] == 24
    assert result["kind"] == "direct"
    assert result["num_changes"] == 0
    assert result["origin_crs"] == "910GWOKING"
    assert result["origin_name"] == "Woking Rail Station"
    assert result["arrival_name"] == "London Waterloo"
    assert result["interchange_crs"] is None
    assert result["operator"] == "South Western Railway"


def test_mid_journey_walking_leg_counts_as_a_change():
    """Old Street -> Tower Hill, confirmed live during issue #47's UX
    review: a walking leg between two transport legs (Bank -> Monument) is
    a real interchange, not access/egress, and must count as a change."""
    legs = [
        _leg("tube", "Old Street Underground Station", "940GZZLUOST", "Bank Underground Station", "940GZZLUBNK"),
        _leg("walking", "Bank Underground Station", "940GZZLUBNK", "Monument Underground Station", "940GZZLUMON", duration=5),
        _leg("tube", "Monument Underground Station", "940GZZLUMON", "Tower Hill Underground Station", "940GZZLUTWH"),
    ]

    extracted = tfl_client._extract_journey(_journey(20, legs))

    assert extracted["num_changes"] == 2
    assert extracted["kind"] == "interchange"
    assert extracted["interchange_crs"] == "940GZZLUBNK, 940GZZLUMON"
    assert extracted["origin_crs"] == "940GZZLUOST"
    assert extracted["arrival_name"] == "Tower Hill Underground Station"


def test_journey_with_no_non_walking_leg_falls_back_to_walking_legs_arrival_point():
    # Destination within walking distance of the raw origin -- no transit
    # leg at all.
    legs = [_leg("walking", "origin", None, "12 Example Street", "postcode-centroid", duration=8)]

    extracted = tfl_client._extract_journey(_journey(8, legs))

    assert extracted["origin_crs"] == "postcode-centroid"
    assert extracted["origin_name"] == "12 Example Street"
    assert extracted["arrival_name"] == "12 Example Street"
    assert extracted["kind"] == "direct"
    assert extracted["num_changes"] == 0


def test_leading_run_of_multiple_walking_legs_is_all_excluded():
    # Two consecutive walking legs before the first transit leg (e.g. a
    # short transfer between two nearby stops) must both be excluded from
    # the change count, not just the very first leg.
    legs = [
        _leg("walking", "origin", None, "Stop A", "910GA", duration=3),
        _leg("walking", "Stop A", "910GA", "Stop B", "910GB", duration=4),
        _leg("national-rail", "Stop B", "910GB", "Destination", "910GC", duration=20, operator="Test Rail"),
    ]

    extracted = tfl_client._extract_journey(_journey(20, legs))

    assert extracted["kind"] == "direct"
    assert extracted["num_changes"] == 0
    assert extracted["origin_crs"] == "910GB"
    assert extracted["origin_name"] == "Stop B"


def test_trailing_run_of_multiple_walking_legs_is_all_excluded():
    legs = [
        _leg("national-rail", "Origin", "910GA", "Stop B", "910GB", duration=20, operator="Test Rail"),
        _leg("walking", "Stop B", "910GB", "Stop C", "910GC", duration=4),
        _leg("walking", "Stop C", "910GC", "Destination", "910GD", duration=3),
    ]

    extracted = tfl_client._extract_journey(_journey(20, legs))

    assert extracted["kind"] == "direct"
    assert extracted["num_changes"] == 0
    assert extracted["arrival_name"] == "Stop B"


def test_duration_minutes_is_read_directly_never_diffed_from_timestamps():
    # startDateTime/arrivalDateTime deliberately don't match `duration` --
    # simulates the DST-ambiguous case the issue #47 spike found live.
    # duration_minutes must come from the `duration` field, not a diff.
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    journey = _journey(24, legs, start="2026-10-25T01:30:00", arrival="2026-10-25T01:30:00")  # same clock time

    extracted = tfl_client._extract_journey(journey)

    assert extracted["duration_minutes"] == 24


def test_walks_pagination_across_pages_and_picks_fastest(monkeypatch):
    legs_slow = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=40, operator="Slow Rail")]
    legs_fast = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=20, operator="Fast Rail")]

    page1 = {"journeys": [_journey(40, legs_slow, start="2026-08-17T08:30:00", arrival="2026-08-17T09:10:00")]}
    page2 = {"journeys": [_journey(20, legs_fast, start="2026-08-17T08:55:00", arrival="2026-08-17T09:15:00")]}
    pages = [page1, page2]

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return _FakeResponse(pages[len(calls) - 1] if len(calls) <= len(pages) else {"journeys": []})

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30)
    )

    assert len(calls) >= 2
    assert result["duration_minutes"] == 20


def test_stops_scanning_once_window_exceeded(monkeypatch):
    # A journey departing well past the 60-minute window must not extend
    # the scan further.
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    page1 = {"journeys": [_journey(24, legs, start="2026-08-17T09:40:00", arrival="2026-08-17T10:04:00")]}

    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(page1)

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    tfl_client.find_frequent_destination_journey(51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30))

    assert len(calls) == 1


def test_returns_none_when_no_journeys_found(monkeypatch):
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"journeys": []}))
    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30)
    )
    assert result is None


def test_returns_none_on_request_failure(monkeypatch):
    def fake_get(url):
        raise tfl_client.TflApiError("boom")

    monkeypatch.setattr(tfl_client, "_get", fake_get)
    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30)
    )
    assert result is None


def test_throttle_is_invoked(monkeypatch):
    calls = []
    monkeypatch.setattr(tfl_client, "_throttle", lambda: calls.append(1))
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"journeys": [_journey(24, legs)]}))

    tfl_client.find_frequent_destination_journey(51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30))

    assert len(calls) >= 1


# --- search_stop_points -------------------------------------------------

def test_search_stop_points_returns_matches(monkeypatch):
    payload = {
        "matches": [
            {"id": "910GPADTON", "name": "London Paddington", "modes": ["national-rail", "elizabeth-line"]},
        ]
    }
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    monkeypatch.setattr(tfl_client, "_throttle", lambda: None)

    results = tfl_client.search_stop_points("paddington")
    assert results == [{"id": "910GPADTON", "name": "London Paddington", "modes": ["national-rail", "elizabeth-line"]}]


def test_search_stop_points_blank_query_returns_empty():
    assert tfl_client.search_stop_points("") == []


def test_search_stop_points_respects_limit(monkeypatch):
    payload = {"matches": [{"id": f"91{i}", "name": f"Station {i}", "modes": ["tube"]} for i in range(10)]}
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    monkeypatch.setattr(tfl_client, "_throttle", lambda: None)

    results = tfl_client.search_stop_points("station", limit=3)
    assert len(results) == 3


def test_search_stop_points_returns_empty_on_error(monkeypatch):
    def raise_error(url):
        raise tfl_client.TflApiError("boom")

    monkeypatch.setattr(tfl_client, "_get", raise_error)
    assert tfl_client.search_stop_points("paddington") == []
