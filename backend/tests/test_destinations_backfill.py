import json
import time

import pytest

from app.destinations import compute, journey_store
from app.listings import store as listings_store

STATIONS_RAW = [{"name": "Woking Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]}]


def _direct_journey(duration_minutes):
    return {
        "journeys": [
            {
                "kind": "direct",
                "departure_time": "08:40:00",
                "arrival_time": "09:04:00",
                "duration_minutes": duration_minutes,
                "is_past": False,
                "direct": {"operator": "South Western Railway"},
                "interchange": None,
            }
        ]
    }


@pytest.fixture
def existing_listing():
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"nearest_stations_raw": json.dumps(STATIONS_RAW)})
    return 1


def _wait_for_backfill(client, destination_id, timeout=2.0):
    """The backfill now runs on a background thread (issue #36) instead of
    inline in the request -- poll the status endpoint this feature adds
    until it reports 'done', same as the frontend will."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/destinations/{destination_id}/backfill-status").json()
        if status["status"] == "done":
            return status
        time.sleep(0.01)
    pytest.fail(f"backfill for destination {destination_id} did not finish within {timeout}s")


def test_create_destination_backfills_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))

    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    destination_id = resp.json()["id"]
    _wait_for_backfill(client, destination_id)

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 24


def test_patch_destination_recomputes_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))
    destination_id = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()["id"]
    _wait_for_backfill(client, destination_id)

    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(40))
    client.patch(f"/api/destinations/{destination_id}", json={"time": "09:00"})
    _wait_for_backfill(client, destination_id)

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 40


def test_disabling_destination_clears_stored_journey_without_touching_others(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))
    office_id = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()["id"]
    _wait_for_backfill(client, office_id)
    home_id = client.post(
        "/api/destinations",
        json={"name": "Mum & Dad's", "crs": "GLD", "station_name": "Guildford", "day_of_week": 6, "time": "12:00"},
    ).json()["id"]
    _wait_for_backfill(client, home_id)

    client.patch(f"/api/destinations/{office_id}", json={"enabled": False})
    _wait_for_backfill(client, office_id)

    journeys = journey_store.get_journeys(existing_listing)
    assert office_id not in journeys
    assert journeys[home_id]["duration_minutes"] == 24


# --- backfill-status endpoint / progress tracking --------------------------


def test_backfill_status_is_idle_for_a_destination_with_no_tracked_run(client):
    resp = client.get("/api/destinations/999/backfill-status")
    assert resp.status_code == 200
    assert resp.json() == {"status": "idle", "done": 0, "total": 0}


def test_backfill_status_reaches_done_with_full_total(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))

    destination_id = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()["id"]

    status = _wait_for_backfill(client, destination_id)
    assert status == {"status": "done", "done": 1, "total": 1}


def test_create_destination_does_not_block_on_backfill(client, existing_listing, monkeypatch):
    """The whole point of issue #36 -- the create request must return before
    the backfill finishes, not after. Uses an event so the fake
    fetch_journeys blocks until the test explicitly releases it, proving the
    POST response doesn't wait on it."""
    import threading

    release = threading.Event()

    def slow_fetch(*a, **k):
        release.wait(timeout=2.0)
        return _direct_journey(24)

    monkeypatch.setattr(compute, "fetch_journeys", slow_fetch)

    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    destination_id = resp.json()["id"]

    # The request already returned above -- the backfill is still blocked on
    # `release`, so it must not be done yet.
    status = client.get(f"/api/destinations/{destination_id}/backfill-status").json()
    assert status["status"] == "running"

    release.set()
    _wait_for_backfill(client, destination_id)
