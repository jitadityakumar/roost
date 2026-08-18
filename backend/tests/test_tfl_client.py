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
    # Real Journey/JourneyResults responses leave departurePoint/
    # arrivalPoint's `id` field null and carry the real StopPoint id under
    # `naptanId` instead (confirmed live, issue #47 follow-up) -- match that
    # shape here, `id` explicitly None, so the fixture can't mask a
    # regression back to reading the wrong field the way it did before
    # _leg_point_id existed.
    leg = {
        "mode": {"id": mode_id},
        "duration": duration,
        "departurePoint": {"commonName": dep_name, "id": None, "naptanId": dep_id},
        "arrivalPoint": {"commonName": arr_name, "id": None, "naptanId": arr_id},
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


def test_scan_requests_least_interchange_and_excludes_bus(monkeypatch):
    # Issue #51: the Frequent Destinations scan must ask TfL for
    # journeyPreference=LeastInterchange and a non-bus mode allowlist, not
    # LeastTime with every mode in play.
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    payload = {"journeys": [_journey(24, legs, start="2026-08-17T09:30:00", arrival="2026-08-17T09:54:00")]}
    requested_urls = []

    def fake_urlopen(req, timeout):
        requested_urls.append(req.full_url)
        return _FakeResponse(payload)

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    tfl_client.find_frequent_destination_journey(51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30))

    assert len(requested_urls) == 1
    assert "journeyPreference=LeastInterchange" in requested_urls[0]
    assert "mode=national-rail%2Ctube%2Coverground%2Cdlr%2Ctram%2Celizabeth-line" in requested_urls[0]


def test_scan_prefers_fewer_changes_over_faster_duration(monkeypatch):
    # Issue #51: a faster-but-more-changes alternative must lose to a
    # slower-but-fewer-changes one -- this is what actually enforces the
    # "avoid bus/extra interchange" preference locally, since TfL's own
    # journeyPreference only shapes what one response contains, not which
    # candidate this code picks as best across a page.
    direct_leg = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=26, operator="Test Rail")]
    changed_legs = [
        _leg("national-rail", "A", "910GA", "C", "910GC", duration=10, operator="Test Rail"),
        _leg("national-rail", "C", "910GC", "B", "910GB", duration=12, operator="Test Rail"),
    ]
    payload = {
        "journeys": [
            _journey(22, changed_legs, start="2026-08-17T08:30:00", arrival="2026-08-17T08:52:00"),
            _journey(26, direct_leg, start="2026-08-17T08:35:00", arrival="2026-08-17T09:01:00"),
        ]
    }
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))

    result = tfl_client.find_frequent_destination_journey(51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30))

    assert result["num_changes"] == 0
    assert result["duration_minutes"] == 26


def test_mid_journey_walking_leg_is_not_an_extra_change():
    """Old Street -> Tower Hill via a walking interchange (Bank -> Monument).
    Confirmed live (issue #47 follow-up): TfL itemises this exact kind of
    transition as a separate walking leg for some journeys and folds it into
    a single leg boundary for others -- e.g. two journeys with the same real
    single bus->train change came back with different leg shapes. Counting
    the walk as an extra change made num_changes depend on how TfL chose to
    itemise the walk rather than on the actual number of transitions, so a
    walking leg (wherever it falls) is excluded entirely and num_changes is
    just len(transit legs) - 1."""
    legs = [
        _leg("tube", "Old Street Underground Station", "940GZZLUOST", "Bank Underground Station", "940GZZLUBNK"),
        _leg("walking", "Bank Underground Station", "940GZZLUBNK", "Monument Underground Station", "940GZZLUMON", duration=5),
        _leg("tube", "Monument Underground Station", "940GZZLUMON", "Tower Hill Underground Station", "940GZZLUTWH"),
    ]

    extracted = tfl_client._extract_journey(_journey(20, legs))

    assert extracted["num_changes"] == 1
    assert extracted["kind"] == "interchange"
    assert extracted["interchange_crs"] == "940GZZLUBNK"
    assert extracted["origin_crs"] == "940GZZLUOST"
    assert extracted["arrival_name"] == "Tower Hill Underground Station"


def test_journey_with_no_non_walking_leg_falls_back_to_walking_legs_arrival_point():
    # Destination within walking distance of the raw origin -- no transit
    # leg at all. A walking leg's arrivalPoint has BOTH id and naptanId null
    # in real TfL responses (confirmed live, issue #47 follow-up) -- pass
    # arr_id=None here (unlike every other test's synthetic id) so this
    # exercises the real shape and origin_crs's name-based fallback, not the
    # naptanId path.
    legs = [_leg("walking", "origin", None, "12 Example Street", None, duration=8)]

    extracted = tfl_client._extract_journey(_journey(8, legs))

    assert extracted["origin_crs"] == "12 Example Street"
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


# --- retry_on_empty (issue #54) -----------------------------------------

def test_retry_on_empty_succeeds_on_third_attempt(monkeypatch):
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    # start pinned to exactly the 60-minute window's edge (target 8:30 + 60m)
    # so this single page's journey both counts (not strictly past the
    # window) and immediately ends the scan (max_departure >= window_end) --
    # otherwise the fake `_get` would need a 4th response for a 2nd page.
    journey = _journey(24, legs, start="2026-08-17T09:30:00", arrival="2026-08-17T09:54:00")
    responses = [{"journeys": []}, {"journeys": []}, {"journeys": [journey]}]

    calls = []

    def fake_get(url):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(tfl_client, "_get", fake_get)
    sleeps = []
    monkeypatch.setattr(tfl_client.time, "sleep", lambda s: sleeps.append(s))

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), retry_on_empty=True
    )

    assert result is not None
    assert result["duration_minutes"] == 24
    assert len(calls) == 3
    assert sleeps == [tfl_client._EMPTY_RESULT_RETRY_DELAY_SECONDS] * 2


def test_retry_on_empty_gives_up_after_max_retries(monkeypatch):
    calls_via_get = []
    monkeypatch.setattr(tfl_client, "_get", lambda url: (calls_via_get.append(url), {"journeys": []})[1])
    sleeps = []
    monkeypatch.setattr(tfl_client.time, "sleep", lambda s: sleeps.append(s))

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), retry_on_empty=True
    )

    assert result is None
    # 3 attempts total (1 + _EMPTY_RESULT_RETRIES), 1 page each since every
    # page comes back empty.
    assert len(calls_via_get) == 1 + tfl_client._EMPTY_RESULT_RETRIES
    assert len(sleeps) == tfl_client._EMPTY_RESULT_RETRIES


def test_retry_on_empty_not_applied_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(tfl_client, "_get", lambda url: (calls.append(url), {"journeys": []})[1])
    sleeps = []
    monkeypatch.setattr(tfl_client.time, "sleep", lambda s: sleeps.append(s))

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30)
    )

    assert result is None
    assert len(calls) == 1
    assert sleeps == []


def test_retry_on_empty_does_not_retry_on_api_error(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        raise tfl_client.TflApiError("boom")

    monkeypatch.setattr(tfl_client, "_get", fake_get)
    sleeps = []
    monkeypatch.setattr(tfl_client.time, "sleep", lambda s: sleeps.append(s))

    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), retry_on_empty=True
    )

    assert result is None
    assert len(calls) == 1
    assert sleeps == []


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


# --- pool_out (issue #59) ------------------------------------------------

def test_pool_out_collects_journeys_across_non_overlapping_pages(monkeypatch):
    legs_a = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    legs_b = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=20, operator="Test Rail")]
    page1 = {"journeys": [_journey(24, legs_a, start="2026-08-17T08:30:00", arrival="2026-08-17T08:54:00")]}
    page2 = {"journeys": [_journey(20, legs_b, start="2026-08-17T08:55:00", arrival="2026-08-17T09:15:00")]}
    pages = [page1, page2]
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(pages[len(calls) - 1] if len(calls) <= len(pages) else {"journeys": []})

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    pool_out = {}
    tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert len(pool_out["candidate_pool"]) == 2
    starts = {j["startDateTime"] for j in pool_out["candidate_pool"]}
    assert starts == {"2026-08-17T08:30:00", "2026-08-17T08:55:00"}


def test_pool_out_dedups_journeys_repeated_across_overlapping_pages(monkeypatch):
    # Reproduces the live-confirmed overlap: page 2 re-returns a journey
    # page 1 already saw (same startDateTime/arrivalDateTime/duration), plus
    # one genuinely new journey.
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    dup_journey = _journey(24, legs, start="2026-08-17T08:30:00", arrival="2026-08-17T08:54:00")
    new_journey = _journey(20, legs, start="2026-08-17T08:56:00", arrival="2026-08-17T09:16:00")
    page1 = {"journeys": [dup_journey]}
    page2 = {"journeys": [dup_journey, new_journey]}
    pages = [page1, page2]
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(pages[len(calls) - 1] if len(calls) <= len(pages) else {"journeys": []})

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    pool_out = {}
    tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert len(pool_out["candidate_pool"]) == 2


def test_pool_out_excludes_journeys_past_window_end(monkeypatch):
    legs_in = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    legs_out = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    payload = {
        "journeys": [
            _journey(24, legs_in, start="2026-08-17T08:40:00", arrival="2026-08-17T09:04:00"),
            # Past the 60-minute window (target 8:30 + 60m = 9:30).
            _journey(24, legs_out, start="2026-08-17T09:40:00", arrival="2026-08-17T10:04:00"),
        ]
    }
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))

    pool_out = {}
    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert result["departure_time"] == "2026-08-17T08:40:00"
    assert len(pool_out["candidate_pool"]) == 1
    assert pool_out["candidate_pool"][0]["startDateTime"] == "2026-08-17T08:40:00"


def test_pool_out_query_params_use_original_target_not_paging_cursor(monkeypatch):
    # Best journey is found on page 2 -- query_params.date/time must still
    # reflect the original target_date/target_time, not the paging cursor
    # (query_date/query_time) the scan had moved on to by page 2.
    legs_slow = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=40, operator="Slow Rail")]
    legs_fast = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=20, operator="Fast Rail")]
    page1 = {"journeys": [_journey(40, legs_slow, start="2026-08-17T08:30:00", arrival="2026-08-17T09:10:00")]}
    page2 = {"journeys": [_journey(20, legs_fast, start="2026-08-17T08:55:00", arrival="2026-08-17T09:15:00")]}
    pages = [page1, page2]
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        return _FakeResponse(pages[len(calls) - 1] if len(calls) <= len(pages) else {"journeys": []})

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)

    pool_out = {}
    tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert pool_out["query_params"]["date"] == "20260817"
    assert pool_out["query_params"]["time"] == "0830"
    assert pool_out["query_params"]["to_identifier"] == "910GB"


def test_pool_out_not_populated_when_no_best_journey(monkeypatch):
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"journeys": []}))

    pool_out = {}
    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert result is None
    assert pool_out == {}


def test_pool_out_omitted_does_not_change_default_behavior(monkeypatch):
    legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=24, operator="Test Rail")]
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"journeys": [_journey(24, legs)]}))

    result = tfl_client.find_frequent_destination_journey(51.3, -0.5, "910GB", dt.date(2026, 8, 17), dt.time(8, 30))

    assert result["duration_minutes"] == 24


def test_pool_out_hub_branch_uses_only_winning_child(monkeypatch):
    children = [
        {"id": "910GCHILD1", "name": "Child One"},
        {"id": "910GCHILD2", "name": "Child Two"},
    ]
    monkeypatch.setattr(tfl_client, "_hub_children", lambda hub_id, modes: children)

    slow_legs = [_leg("national-rail", "A", "910GA", "B", "910GB", duration=40, operator="Slow Rail")]
    fast_legs = [_leg("national-rail", "A", "910GA", "C", "910GC", duration=20, operator="Fast Rail")]

    def fake_scan_journeys(origin_lat, origin_lon, to_identifier, target_date, target_time, retry_on_empty=False, pool_out=None):
        if to_identifier == "910GCHILD1":
            journey = tfl_client._extract_journey(_journey(40, slow_legs))
            if pool_out is not None:
                pool_out["query_params"] = {
                    "journeyPreference": "LeastInterchange",
                    "mode": tfl_client._DESTINATION_SEARCH_MODES,
                    "date": target_date.strftime("%Y%m%d"),
                    "time": target_time.strftime("%H%M"),
                    "to_identifier": to_identifier,
                }
                pool_out["candidate_pool"] = [_journey(40, slow_legs)]
            return journey
        journey = tfl_client._extract_journey(_journey(20, fast_legs))
        if pool_out is not None:
            pool_out["query_params"] = {
                "journeyPreference": "LeastInterchange",
                "mode": tfl_client._DESTINATION_SEARCH_MODES,
                "date": target_date.strftime("%Y%m%d"),
                "time": target_time.strftime("%H%M"),
                "to_identifier": to_identifier,
            }
            pool_out["candidate_pool"] = [_journey(20, fast_legs)]
        return journey

    monkeypatch.setattr(tfl_client, "_scan_journeys", fake_scan_journeys)

    pool_out = {}
    result = tfl_client.find_frequent_destination_journey(
        51.3, -0.5, "HUBTEST", dt.date(2026, 8, 17), dt.time(8, 30), pool_out=pool_out
    )

    assert result["duration_minutes"] == 20
    assert pool_out["query_params"]["to_identifier"] == "910GCHILD2"
    assert pool_out["query_params"]["to_name"] == "Child Two"
    assert len(pool_out["candidate_pool"]) == 1
    assert pool_out["candidate_pool"][0]["duration"] == 20
