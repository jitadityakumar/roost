import threading
import time

import pytest

from app.destinations import backfill_status, compute, journey_store
from app.destinations import store as destinations_store
from app.listings import store as listings_store

LAT, LON = 51.319, -0.559

_CREATE_BODY = {
    "name": "Office",
    "destination_type": "station",
    "tfl_identifier": "910GPADTON",
    "station_name": "Paddington",
    "day_of_week": 0,
    "time": "08:30",
}


def _direct_journey(duration_minutes):
    return {
        "duration_minutes": duration_minutes,
        "kind": "direct",
        "num_changes": 0,
        "operator": "South Western Railway",
        "origin_crs": "910GWOKING",
        "origin_name": "Woking Rail Station",
        "arrival_name": "London Paddington",
        "interchange_crs": None,
        "departure_time": "2026-08-17T08:40:00",
        "arrival_time": "2026-08-17T09:04:00",
    }


@pytest.fixture
def existing_listing():
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"latitude": LAT, "longitude": LON})
    return 1


def _wait_for_backfill(client, destination_id, timeout=2.0):
    """The backfill now runs on backfill_queue's single global worker
    thread (issue #36, serialized as a follow-up) instead of inline in the
    request -- poll the status endpoint this feature adds until it reports
    'done', same as the frontend will."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/destinations/{destination_id}/backfill-status").json()
        if status["status"] == "done":
            return status
        time.sleep(0.01)
    pytest.fail(f"backfill for destination {destination_id} did not finish within {timeout}s")


def test_create_destination_backfills_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(24))

    resp = client.post("/api/destinations", json=_CREATE_BODY)
    destination_id = resp.json()["id"]
    _wait_for_backfill(client, destination_id)

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 24


def test_patch_destination_recomputes_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(24))
    destination_id = client.post("/api/destinations", json=_CREATE_BODY).json()["id"]
    _wait_for_backfill(client, destination_id)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(40))
    client.patch(f"/api/destinations/{destination_id}", json={"time": "09:00"})
    _wait_for_backfill(client, destination_id)

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 40


def test_disabling_destination_clears_stored_journey_without_touching_others(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(24))
    office_id = client.post("/api/destinations", json=_CREATE_BODY).json()["id"]
    _wait_for_backfill(client, office_id)
    home_id = client.post(
        "/api/destinations",
        json={
            "name": "Mum & Dad's",
            "destination_type": "station",
            "tfl_identifier": "910GGLDFD",
            "station_name": "Guildford",
            "day_of_week": 6,
            "time": "12:00",
        },
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
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(24))

    destination_id = client.post("/api/destinations", json=_CREATE_BODY).json()["id"]

    status = _wait_for_backfill(client, destination_id)
    assert status == {"status": "done", "done": 1, "total": 1}


def test_create_destination_does_not_block_on_backfill(client, existing_listing, monkeypatch):
    """The whole point of issue #36 -- the create request must return before
    the backfill finishes, not after. Uses an event so the fake journey
    lookup blocks until the test explicitly releases it, proving the POST
    response doesn't wait on it."""
    release = threading.Event()

    def slow_journey(*a, **k):
        release.wait(timeout=2.0)
        return _direct_journey(24)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", slow_journey)

    resp = client.post("/api/destinations", json=_CREATE_BODY)
    destination_id = resp.json()["id"]

    # The request already returned above -- the backfill is still blocked on
    # `release`, so it must not be done yet. Accept either 'queued' or
    # 'running': backfill_queue's worker thread picks the job up
    # asynchronously, so there's a small, non-deterministic window right
    # after the response where it may not have transitioned to 'running'
    # yet -- both states mean "not finished", which is what this test is
    # actually asserting.
    status = client.get(f"/api/destinations/{destination_id}/backfill-status").json()
    assert status["status"] in ("queued", "running")

    release.set()
    _wait_for_backfill(client, destination_id)


def test_compute_for_destination_marks_backfill_failed_on_exception(existing_listing, monkeypatch):
    """Code-review follow-up on issue #36: a mid-backfill exception must not
    leave backfill_status stuck on 'running' forever -- the status route
    would otherwise report a dead backfill as still in progress
    indefinitely. Calls compute_for_destination directly (bypassing the
    route/thread) so the exception can be asserted on directly instead of
    only observed as a background-thread warning."""
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _direct_journey(24))
    d = destinations_store.create_destination(
        "Office", "station", "910GPADTON", "Paddington", 0, "08:30"
    )

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(compute.journey_store, "replace_single", boom)

    # Mirrors what backfill_queue.enqueue()/the worker do before calling
    # compute_for_destination (start() then mark_running()).
    backfill_status.start(d["id"], total=1)
    backfill_status.mark_running(d["id"])

    with pytest.raises(RuntimeError):
        compute.compute_for_destination(d["id"])

    assert backfill_status.get(d["id"])["status"] == "failed"


def test_patch_while_a_backfill_is_already_running_is_queued_not_dropped(client, existing_listing, monkeypatch):
    """Code-review follow-up on issue #36: a PATCH arriving while an earlier
    backfill (from create, or a previous PATCH) is still running must not be
    silently dropped -- it should run once the in-flight one finishes,
    picking up the destination's fields as of whenever it actually runs."""
    first_call_release = threading.Event()
    calls = []

    def find_journey(lat, lon, to_identifier, target_date, target_time):
        calls.append(target_time)
        if len(calls) == 1:
            first_call_release.wait(timeout=2.0)
            return _direct_journey(24)
        return _direct_journey(40)

    monkeypatch.setattr(compute, "find_frequent_destination_journey", find_journey)

    destination_id = client.post("/api/destinations", json=_CREATE_BODY).json()["id"]

    # The create's backfill is now blocked inside find_frequent_destination_journey.
    # A PATCH arriving while it's still in flight ('queued' or 'running' --
    # see the comment in test_create_destination_does_not_block_on_backfill
    # for why both are accepted) must still succeed and must not get dropped.
    status_before_patch = client.get(f"/api/destinations/{destination_id}/backfill-status").json()
    assert status_before_patch["status"] in ("queued", "running")

    resp = client.patch(f"/api/destinations/{destination_id}", json={"time": "09:00"})
    assert resp.status_code == 200

    first_call_release.set()

    # Don't rely on backfill-status transiently reading 'done' here -- it
    # flips 'running' -> 'done' -> 'running' (queued rerun) -> 'done' again,
    # and polling status alone can't distinguish which 'done' it caught.
    # Poll the actual stored value instead: only the rerun (using the
    # PATCH's 09:00) can produce 40.
    deadline = time.monotonic() + 2.0
    duration = None
    while time.monotonic() < deadline:
        journeys = journey_store.get_journeys(existing_listing)
        duration = journeys.get(destination_id, {}).get("duration_minutes")
        if duration == 40:
            break
        time.sleep(0.01)

    assert duration == 40, "PATCH's backfill was dropped instead of queued behind the running one"
