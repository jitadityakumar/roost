import json

import pytest

from app.listings import store


@pytest.fixture
def listing_id(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(
        1,
        {
            "nearest_stations_raw": json.dumps(
                [{"name": "Woking Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]}]
            )
        },
    )
    return 1


def test_get_destinations_404_for_unknown_listing(client):
    resp = client.get("/api/listings/999/destinations")
    assert resp.status_code == 404


def test_get_destinations_empty_when_none_configured(client, listing_id):
    resp = client.get(f"/api/listings/{listing_id}/destinations")
    assert resp.json() == []


def test_get_destinations_shows_unresolved_when_no_stored_journey(client, listing_id):
    client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    resp = client.get(f"/api/listings/{listing_id}/destinations")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["resolved"] is False
    assert body[0]["name"] == "Office"
    assert body[0]["day_label"] == "Monday"
    assert body[0]["station_name"] == "Paddington"
    assert body[0]["crs"] == "PAD"


def test_refresh_destinations_computes_and_returns_result(client, listing_id, monkeypatch):
    client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )

    from app.destinations import compute

    def fake_fetch_journeys(from_crs, to_crs, date, time):
        return {
            "journeys": [
                {
                    "kind": "direct",
                    "departure_time": "08:40:00",
                    "arrival_time": "09:04:00",
                    "duration_minutes": 24,
                    "is_past": False,
                    "direct": {"operator": "South Western Railway"},
                    "interchange": None,
                }
            ]
        }

    monkeypatch.setattr(compute, "fetch_journeys", fake_fetch_journeys)

    resp = client.post(f"/api/listings/{listing_id}/destinations/refresh")
    assert resp.status_code == 202
    body = resp.json()
    assert body[0]["resolved"] is True
    assert body[0]["duration_minutes"] == 24
    assert body[0]["origin_crs"] == "WOK"

    # And a plain GET afterwards reflects the same stored result.
    resp = client.get(f"/api/listings/{listing_id}/destinations")
    assert resp.json()[0]["duration_minutes"] == 24
