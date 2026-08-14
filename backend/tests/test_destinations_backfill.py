import json

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


def test_create_destination_backfills_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))

    resp = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    )
    destination_id = resp.json()["id"]

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 24


def test_patch_destination_recomputes_existing_listings(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))
    destination_id = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()["id"]

    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(40))
    client.patch(f"/api/destinations/{destination_id}", json={"time": "09:00"})

    journeys = journey_store.get_journeys(existing_listing)
    assert journeys[destination_id]["duration_minutes"] == 40


def test_disabling_destination_clears_stored_journey_without_touching_others(client, existing_listing, monkeypatch):
    monkeypatch.setattr(compute, "fetch_journeys", lambda *a, **k: _direct_journey(24))
    office_id = client.post(
        "/api/destinations",
        json={"name": "Office", "crs": "PAD", "station_name": "Paddington", "day_of_week": 0, "time": "08:30"},
    ).json()["id"]
    home_id = client.post(
        "/api/destinations",
        json={"name": "Mum & Dad's", "crs": "GLD", "station_name": "Guildford", "day_of_week": 6, "time": "12:00"},
    ).json()["id"]

    client.patch(f"/api/destinations/{office_id}", json={"enabled": False})

    journeys = journey_store.get_journeys(existing_listing)
    assert office_id not in journeys
    assert journeys[home_id]["duration_minutes"] == 24
