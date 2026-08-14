import datetime as dt

import pytest

from app.destinations import compute, journey_store, store
from app.destinations.client import TrainPlannerApiError
from app.listings import store as listings_store

STATIONS_RAW = [
    {"name": "Woking Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]},
    {"name": "Clapham Junction Station", "distance": 0.6, "types": ["NATIONAL_TRAIN"]},
]


@pytest.fixture(autouse=True)
def listing():
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")


def _journey(duration_minutes, kind="direct", operator="South Western Railway", is_past=False):
    if kind == "direct":
        return {
            "kind": "direct",
            "departure_time": "08:40:00",
            "arrival_time": "09:04:00",
            "duration_minutes": duration_minutes,
            "is_past": is_past,
            "direct": {"operator": operator},
            "interchange": None,
        }
    return {
        "kind": "interchange",
        "departure_time": "08:35:00",
        "arrival_time": "09:10:00",
        "duration_minutes": duration_minutes,
        "is_past": is_past,
        "direct": None,
        "interchange": {"leg1": {"operator": operator}},
    }


# --- next_occurrence --------------------------------------------------------

def test_next_occurrence_later_today():
    now = dt.datetime(2026, 8, 17, 8, 0)  # Monday
    result = compute.next_occurrence(0, "08:30", now=now)
    assert result == dt.datetime(2026, 8, 17, 8, 30)


def test_next_occurrence_rolls_to_next_week_when_time_already_passed_today():
    now = dt.datetime(2026, 8, 17, 9, 0)  # Monday, past 08:30
    result = compute.next_occurrence(0, "08:30", now=now)
    assert result == dt.datetime(2026, 8, 24, 8, 30)


def test_next_occurrence_finds_next_matching_weekday():
    now = dt.datetime(2026, 8, 19, 12, 0)  # Wednesday
    result = compute.next_occurrence(0, "08:30", now=now)  # next Monday
    assert result == dt.datetime(2026, 8, 24, 8, 30)


# --- compute_for_listing -----------------------------------------------

def test_compute_for_listing_picks_best_across_origins(monkeypatch):
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")

    def fake_fetch_journeys(from_crs, to_crs, date, time):
        if from_crs == "WOK":
            return {"journeys": [_journey(24)]}
        return {"journeys": [_journey(40)]}

    monkeypatch.setattr(compute, "fetch_journeys", fake_fetch_journeys)
    compute.compute_for_listing(1, STATIONS_RAW)

    journeys = journey_store.get_journeys(1)
    assert journeys[d["id"]]["duration_minutes"] == 24
    assert journeys[d["id"]]["origin_crs"] == "WOK"
    assert journeys[d["id"]]["operator"] == "South Western Railway"


def test_compute_for_listing_skips_origin_on_api_error(monkeypatch):
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")

    def fake_fetch_journeys(from_crs, to_crs, date, time):
        if from_crs == "WOK":
            raise TrainPlannerApiError("boom")
        return {"journeys": [_journey(40)]}

    monkeypatch.setattr(compute, "fetch_journeys", fake_fetch_journeys)
    compute.compute_for_listing(1, STATIONS_RAW)

    journeys = journey_store.get_journeys(1)
    assert journeys[d["id"]]["duration_minutes"] == 40
    assert journeys[d["id"]]["origin_crs"] == "CLJ"


def test_compute_for_listing_stores_nothing_when_no_route_found(monkeypatch):
    store.create_destination("Office", "PAD", "Paddington", 0, "08:30")

    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: {"journeys": []})
    compute.compute_for_listing(1, STATIONS_RAW)

    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_ignores_disabled_destination(monkeypatch):
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")
    store.update_destination(d["id"], enabled=False)

    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: {"journeys": [_journey(24)]})
    compute.compute_for_listing(1, STATIONS_RAW)

    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_prefers_upcoming_over_past_journeys(monkeypatch):
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")

    def fake_fetch_journeys(from_crs, to_crs, date, time):
        return {"journeys": [_journey(10, is_past=True), _journey(24)]}

    monkeypatch.setattr(compute, "fetch_journeys", fake_fetch_journeys)
    compute.compute_for_listing(1, STATIONS_RAW)

    journeys = journey_store.get_journeys(1)
    assert journeys[d["id"]]["duration_minutes"] == 24


def test_compute_for_listing_stores_nothing_when_every_journey_is_past(monkeypatch):
    store.create_destination("Office", "PAD", "Paddington", 0, "08:30")

    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: {"journeys": [_journey(10, is_past=True)]})
    compute.compute_for_listing(1, STATIONS_RAW)

    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_no_candidate_stations_stores_nothing(monkeypatch):
    store.create_destination("Office", "PAD", "Paddington", 0, "08:30")
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: pytest.fail("should not be called"))
    compute.compute_for_listing(1, [])
    assert journey_store.get_journeys(1) == {}
