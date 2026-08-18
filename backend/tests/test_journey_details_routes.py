from app.destinations import journey_store, store
from app.listings import store as listings_store

LAT, LON = 51.319, -0.559


def _row(destination_id):
    return {
        "destination_id": destination_id,
        "duration_minutes": 24,
        "kind": "direct",
        "num_changes": 0,
        "operator": "South Western Railway",
        "origin_crs": "910GWOKING",
        "origin_name": "Woking Rail Station",
        "arrival_name": "Paddington",
        "interchange_crs": None,
        "departure_time": "2026-08-17T08:40:00",
        "arrival_time": "2026-08-17T09:04:00",
    }


def _journey_with_legs():
    return {
        "startDateTime": "2026-08-17T08:04:00",
        "arrivalDateTime": "2026-08-17T09:22:00",
        "duration": 78,
        "legs": [
            {
                "mode": {"id": "walking"},
                "duration": 21,
                "departureTime": "2026-08-17T08:04:00",
                "arrivalTime": "2026-08-17T08:25:00",
                "departurePoint": {"commonName": "91 York Road"},
                "arrivalPoint": {"commonName": "Woking Rail Station", "naptanId": "910GWOKING"},
            },
            {
                "mode": {"id": "national-rail"},
                "duration": 26,
                "departureTime": "2026-08-17T08:25:00",
                "arrivalTime": "2026-08-17T08:51:00",
                "departurePoint": {"commonName": "Woking Rail Station", "naptanId": "910GWOKING"},
                "arrivalPoint": {"commonName": "London Waterloo", "naptanId": "910GWATRLMN"},
                "routeOptions": [{"name": "South Western Railway"}],
            },
            {
                "mode": {"id": "tube"},
                "duration": 12,
                # 8m gap after the previous leg's 08:51 arrival.
                "departureTime": "2026-08-17T08:59:00",
                "arrivalTime": "2026-08-17T09:11:00",
                "departurePoint": {"commonName": "London Waterloo", "naptanId": "910GWATRLMN"},
                "arrivalPoint": {"commonName": "Mornington Crescent", "naptanId": "940GZZLUMTC"},
                "routeOptions": [{"name": "Northern line"}],
            },
        ],
    }


def _create_destination():
    return store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")


def _create_pool(listing_id=1, destination_id=None, journeys=None):
    journey_store.replace_single(
        listing_id,
        destination_id,
        _row(destination_id),
        {
            "query_params": {
                "journeyPreference": "LeastInterchange",
                "mode": "national-rail,tube,overground,dlr,tram,elizabeth-line",
                "date": "20260825",
                "time": "0800",
                "to_identifier": "910GPADTON",
            },
            "candidate_pool": journeys if journeys is not None else [_journey_with_legs()],
        },
    )


def test_get_scan_pool_404_for_missing_id(client):
    resp = client.get("/api/journey-scan-pools/999")
    assert resp.status_code == 404


def test_get_scan_pool_returns_parsed_candidates(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"latitude": LAT, "longitude": LON})
    d = _create_destination()
    _create_pool(destination_id=d["id"])
    pool_id = journey_store.get_scan_pool_ids(1)[d["id"]]

    resp = client.get(f"/api/journey-scan-pools/{pool_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["destination_name"] == "Office"
    assert body["query_params"]["to_identifier"] == "910GPADTON"
    assert len(body["candidates"]) == 1

    candidate = body["candidates"][0]
    assert candidate["duration_minutes"] == 78
    assert candidate["num_changes"] == 1
    assert len(candidate["legs"]) == 3

    walk_leg, rail_leg, tube_leg = candidate["legs"]
    assert walk_leg["mode"] == "walking"
    assert walk_leg["operator"] is None
    assert "change_minutes" not in walk_leg

    assert rail_leg["operator"] == "South Western Railway"
    assert rail_leg["change_minutes"] == 8

    assert tube_leg["operator"] == "Northern line"
    assert "change_minutes" not in tube_leg
