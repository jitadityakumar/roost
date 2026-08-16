import datetime as dt

import pytest

from app import config
from app.destinations import compute, journey_store, store
from app.listings import store as listings_store

LAT, LON = 51.319, -0.559  # Woking-area coordinates, matches the issue #47 spike


@pytest.fixture(autouse=True)
def listing():
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"latitude": LAT, "longitude": LON})


def _journey(
    duration_minutes=24,
    kind="direct",
    num_changes=0,
    operator="South Western Railway",
    origin_crs="910GWOKING",
    origin_name="Woking Rail Station",
    arrival_name="Paddington",
    interchange_crs=None,
):
    return {
        "duration_minutes": duration_minutes,
        "kind": kind,
        "num_changes": num_changes,
        "operator": operator,
        "origin_crs": origin_crs,
        "origin_name": origin_name,
        "arrival_name": arrival_name,
        "interchange_crs": interchange_crs,
        "departure_time": "2026-08-17T08:40:00",
        "arrival_time": "2026-08-17T09:04:00",
    }


def _create_destination(tfl_identifier="910GPADTON", destination_type="station", station_name="Paddington"):
    return store.create_destination("Office", destination_type, tfl_identifier, station_name, 0, "08:30")


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

def test_compute_for_listing_stores_a_found_journey(monkeypatch):
    d = _create_destination()

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(24))
    compute.compute_for_listing(1, LAT, LON)

    journeys = journey_store.get_journeys(1)
    assert journeys[d["id"]]["duration_minutes"] == 24
    assert journeys[d["id"]]["origin_crs"] == "910GWOKING"
    assert journeys[d["id"]]["origin_name"] == "Woking Rail Station"
    assert journeys[d["id"]]["arrival_name"] == "Paddington"
    assert journeys[d["id"]]["operator"] == "South Western Railway"


def test_compute_for_listing_stores_interchange_crs_for_a_change_journey(monkeypatch):
    d = _create_destination()

    monkeypatch.setattr(
        compute,
        "find_frequent_destination_journey",
        lambda *a, **k: _journey(45, kind="interchange", num_changes=1, interchange_crs="910GCLPHMJ"),
    )
    compute.compute_for_listing(1, LAT, LON)

    journey = journey_store.get_journeys(1)[d["id"]]
    assert journey["kind"] == "interchange"
    assert journey["num_changes"] == 1
    assert journey["interchange_crs"] == "910GCLPHMJ"


def test_compute_for_listing_direct_journey_has_no_interchange_crs(monkeypatch):
    d = _create_destination()

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(24))
    compute.compute_for_listing(1, LAT, LON)

    journey = journey_store.get_journeys(1)[d["id"]]
    assert journey["interchange_crs"] is None


def test_compute_for_listing_stores_nothing_when_no_journey_found(monkeypatch):
    _create_destination()

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    compute.compute_for_listing(1, LAT, LON)

    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_ignores_disabled_destination(monkeypatch):
    d = _create_destination()
    store.update_destination(d["id"], enabled=False)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(24))
    compute.compute_for_listing(1, LAT, LON)

    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_no_lat_lon_stores_nothing(monkeypatch):
    _create_destination()
    monkeypatch.setattr(
        compute, "find_frequent_destination_journey", lambda *a, **k: pytest.fail("should not be called")
    )
    compute.compute_for_listing(1, None, None)
    assert journey_store.get_journeys(1) == {}


def test_compute_for_listing_skips_destination_with_no_tfl_identifier(monkeypatch):
    # Simulates a post-migration-0019 row whose tfl_identifier hasn't been
    # re-picked yet (nullable at the DB level, see migration 0019).
    d = store.create_destination("Office", "station", "PLACEHOLDER", "Paddington", 0, "08:30")
    store.update_destination(d["id"], tfl_identifier="")
    monkeypatch.setattr(
        compute, "find_frequent_destination_journey", lambda *a, **k: pytest.fail("should not be called")
    )
    compute.compute_for_listing(1, LAT, LON)
    assert journey_store.get_journeys(1) == {}


# --- compute_for_destination -------------------------------------------

def test_compute_for_destination_backfills_every_listing(monkeypatch):
    d = _create_destination()
    listings_store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    listings_store.apply_extracted_fields(2, {"latitude": LAT, "longitude": LON})

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(24))
    compute.compute_for_destination(d["id"])

    assert journey_store.get_journeys(1)[d["id"]]["duration_minutes"] == 24
    assert journey_store.get_journeys(2)[d["id"]]["duration_minutes"] == 24


def test_compute_for_destination_disabled_clears_rows(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(24))
    compute.compute_for_listing(1, LAT, LON)
    assert journey_store.get_journeys(1) != {}

    store.update_destination(d["id"], enabled=False)
    d = next(dd for dd in store.list_destinations() if dd["id"] == d["id"])
    compute.compute_for_destination(d["id"])

    assert journey_store.get_journeys(1) == {}


# --- compute_home_journey -----------------------------------------------

def test_compute_home_journey_stores_when_home_configured(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(42))

    compute.compute_home_journey(d)

    home = journey_store.get_home_journeys()[d["id"]]
    assert home["duration_minutes"] == 42
    assert home["kind"] == "direct"
    assert home["num_changes"] == 0


def test_compute_home_journey_uses_home_coords_as_origin(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    seen = {}

    def fake_journey(lat, lon, *a, **k):
        seen["lat"], seen["lon"] = lat, lon
        return _journey(42)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", fake_journey)
    compute.compute_home_journey(d)

    assert seen == {"lat": 51.465, "lon": -0.2407}


def test_compute_home_journey_clears_when_home_not_configured(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", None)
    monkeypatch.setattr(config, "HOME_LON", None)
    monkeypatch.setattr(
        compute, "find_frequent_destination_journey", lambda *a, **k: pytest.fail("should not be called")
    )

    compute.compute_home_journey(d)

    assert journey_store.get_home_journeys() == {}


def test_compute_home_journey_clears_when_destination_disabled(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(42))
    compute.compute_home_journey(d)
    assert journey_store.get_home_journeys() != {}

    disabled = dict(d, enabled=0)
    compute.compute_home_journey(disabled)

    assert journey_store.get_home_journeys() == {}


def test_compute_home_journey_clears_when_configured_but_no_journey_found(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(42))
    compute.compute_home_journey(d)
    assert journey_store.get_home_journeys() != {}

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    compute.compute_home_journey(d)

    assert journey_store.get_home_journeys() == {}


def test_compute_for_destination_also_computes_home_journey(monkeypatch):
    d = _create_destination()
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _journey(42))

    compute.compute_for_destination(d["id"])

    assert journey_store.get_home_journeys()[d["id"]]["duration_minutes"] == 42
