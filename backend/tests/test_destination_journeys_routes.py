import pytest

from app.listings import store

_CREATE_BODY = {
    "name": "Office",
    "destination_type": "station",
    "tfl_identifier": "910GPADTON",
    "station_name": "Paddington",
    "day_of_week": 0,
    "time": "08:30",
}


@pytest.fixture
def listing_id(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(1, {"latitude": 51.319, "longitude": -0.559})
    return 1


def test_get_destinations_404_for_unknown_listing(client):
    resp = client.get("/api/listings/999/destinations")
    assert resp.status_code == 404


def test_get_destinations_empty_when_none_configured(client, listing_id):
    resp = client.get(f"/api/listings/{listing_id}/destinations")
    assert resp.json() == []


def test_get_destinations_shows_unresolved_when_no_stored_journey(client, listing_id, monkeypatch):
    from app.destinations import compute

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    client.post("/api/destinations", json=_CREATE_BODY)

    resp = client.get(f"/api/listings/{listing_id}/destinations")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["resolved"] is False
    assert body[0]["name"] == "Office"
    assert body[0]["day_label"] == "Monday"
    assert body[0]["station_name"] == "Paddington"
    assert body[0]["destination_type"] == "station"


def test_refresh_destinations_computes_and_returns_result(client, listing_id, monkeypatch):
    from app.destinations import compute

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    client.post("/api/destinations", json=_CREATE_BODY)

    def fake_journey(lat, lon, to_identifier, target_date, target_time):
        return {
            "duration_minutes": 24,
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

    monkeypatch.setattr(compute, "find_frequent_destination_journey", fake_journey)

    resp = client.post(f"/api/listings/{listing_id}/destinations/refresh")
    assert resp.status_code == 202
    body = resp.json()
    assert body[0]["resolved"] is True
    assert body[0]["duration_minutes"] == 24
    assert body[0]["origin_name"] == "Woking Rail Station"
    assert body[0]["arrival_name"] == "London Paddington"

    # And a plain GET afterwards reflects the same stored result.
    resp = client.get(f"/api/listings/{listing_id}/destinations")
    assert resp.json()[0]["duration_minutes"] == 24


def test_refresh_destinations_omits_home_diff_when_no_home_configured(client, listing_id, monkeypatch):
    from app.destinations import compute

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    client.post("/api/destinations", json=_CREATE_BODY)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(24))

    resp = client.post(f"/api/listings/{listing_id}/destinations/refresh")
    assert "home_duration_diff_minutes" not in resp.json()[0]


def test_refresh_destinations_includes_home_diff_when_home_configured(client, listing_id, monkeypatch):
    from app import config
    from app.destinations import backfill_queue, compute, journey_store

    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: None)
    resp = client.post("/api/destinations", json=_CREATE_BODY)
    destination_id = resp.json()["id"]
    # Wait for create's background backfill (which also computes the home
    # journey, currently None since find_frequent_destination_journey is
    # stubbed to None above) to finish before overwriting it below --
    # otherwise the background thread could clear the manually-seeded row
    # right after this test sets it.
    backfill_queue.wait_until_idle(timeout=5)
    journey_store.set_home_journey(destination_id, {"duration_minutes": 18, "kind": "direct", "num_changes": 0})

    monkeypatch.setattr(compute, "find_frequent_destination_journey", lambda *a, **k: _fake_journey(42))
    resp = client.post(f"/api/listings/{listing_id}/destinations/refresh")

    assert resp.json()[0]["home_duration_diff_minutes"] == 42 - 18


def _fake_journey(duration_minutes):
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
