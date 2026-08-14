import json

import pytest

from app.commute.stations import resolve_crs_codes, search_stations
from app.listings import store


# --- client ----------------------------------------------------------------

def test_fetch_station_termini_raises_clearly_when_api_base_unset(monkeypatch):
    from app.commute import client

    monkeypatch.setattr(client, "COMMUTE_API_BASE", None)
    with pytest.raises(client.CommuteApiError, match="ROOST_COMMUTE_API_BASE"):
        client.fetch_station_termini("CLJ")


# --- station resolution -----------------------------------------------

def test_resolve_strips_station_suffix_and_looks_up_crs():
    stations = [{"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]}]
    resolved = resolve_crs_codes(stations)
    assert resolved == [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4}]


def test_resolve_keeps_parenthetical_suffix():
    stations = [{"name": "Earlswood (Surrey) Station", "distance": 0.3, "types": ["NATIONAL_TRAIN"]}]
    resolved = resolve_crs_codes(stations)
    assert resolved == [{"name": "Earlswood (Surrey)", "crs": "ELD", "distance": 0.3}]


def test_resolve_excludes_non_national_rail_entries():
    stations = [{"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]}]
    assert resolve_crs_codes(stations) == []


def test_resolve_drops_unmatched_names_without_erroring():
    stations = [{"name": "Not A Real Station", "distance": 0.1, "types": ["NATIONAL_TRAIN"]}]
    assert resolve_crs_codes(stations) == []


def test_resolve_dedupes_by_crs():
    stations = [
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
        {"name": "Clapham Junction Station", "distance": 0.5, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert len(resolved) == 1


def test_resolve_includes_all_stations_within_a_mile():
    stations = [
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
        {"name": "Woking Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]},
        {"name": "Barnes Station", "distance": 1.0, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert {r["crs"] for r in resolved} == {"CLJ", "WOK", "BNS"}


def test_resolve_excludes_stations_beyond_a_mile():
    stations = [
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
        {"name": "Guildford Station", "distance": 1.01, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert [r["crs"] for r in resolved] == ["CLJ"]


def test_resolve_returns_everything_when_no_station_has_a_distance():
    stations = [
        {"name": "Clapham Junction Station", "distance": None, "types": ["NATIONAL_TRAIN"]},
        {"name": "Woking Station", "distance": None, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert {r["crs"] for r in resolved} == {"CLJ", "WOK"}


def test_resolve_normalizes_periods_against_unpunctuated_csv_name():
    # Rightmove sends "St. Helier Station"; stations.csv has "St Helier"
    # (no period) -- real mismatch found live against listing 175007846.
    stations = [{"name": "St. Helier Station", "distance": 0.45, "types": ["NATIONAL_TRAIN"]}]
    resolved = resolve_crs_codes(stations)
    assert [r["crs"] for r in resolved] == ["SIH"]


def test_resolve_normalizes_curly_apostrophe():
    stations = [{"name": "St James’ Park Station", "distance": 0.1, "types": ["NATIONAL_TRAIN"]}]
    resolved = resolve_crs_codes(stations)
    assert [r["crs"] for r in resolved] == ["SJP"]


def test_resolve_does_not_collapse_whitespace_across_distinct_stations():
    # "How Wood" (HWW) and "Howwood" (HOZ) are genuinely different stations
    # -- normalization must not strip the space between "How" and "Wood".
    stations = [
        {"name": "How Wood Station", "distance": 0.1, "types": ["NATIONAL_TRAIN"]},
        {"name": "Howwood Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert {r["crs"] for r in resolved} == {"HWW", "HOZ"}


# --- route ---------------------------------------------------------------

@pytest.fixture
def listing_id(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(
        1,
        {
            "nearest_stations_raw": json.dumps(
                [
                    {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
                    {"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]},
                ]
            )
        },
    )
    return 1


def test_get_commute_404_for_unknown_listing(client):
    resp = client.get("/api/listings/999/commute")
    assert resp.status_code == 404


def test_get_commute_returns_termini_on_success(client, listing_id, monkeypatch):
    from app.routes import commute as commute_route

    monkeypatch.setattr(
        commute_route, "fetch_station_termini", lambda crs: {"crs": crs, "peak": {"termini": []}}
    )
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stations"] == [
        {
            "name": "Clapham Junction",
            "crs": "CLJ",
            "distance": 0.4,
            "termini": {"crs": "CLJ", "peak": {"termini": []}},
            "error": None,
            "walk_distance_meters": None,
            "walk_duration_seconds": None,
            "walk_maps_url": None,
        }
    ]


def test_get_commute_reports_per_station_error_without_failing_request(client, listing_id, monkeypatch):
    from app.commute.client import CommuteApiError
    from app.routes import commute as commute_route

    def raise_error(crs):
        raise CommuteApiError("boom")

    monkeypatch.setattr(commute_route, "fetch_station_termini", raise_error)
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert resp.status_code == 200
    station = resp.json()["stations"][0]
    assert station["termini"] is None
    assert "boom" in station["error"]


def test_get_commute_empty_when_no_national_rail_stations(client):
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    store.apply_extracted_fields(
        2,
        {"nearest_stations_raw": json.dumps([{"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]}])},
    )
    resp = client.get("/api/listings/2/commute")
    assert resp.status_code == 200
    assert resp.json() == {"stations": []}


def test_get_commute_includes_walk_distance_and_maps_url_when_stored(client, listing_id):
    from app.commute.walk_store import replace_walk_distances

    store.apply_extracted_fields(listing_id, {"latitude": 51.4695, "longitude": -0.1706})
    replace_walk_distances(listing_id, [{"crs": "CLJ", "distance_meters": 500, "duration_seconds": 360}])

    resp = client.get(f"/api/listings/{listing_id}/commute")
    station = resp.json()["stations"][0]
    assert station["walk_distance_meters"] == 500
    assert station["walk_duration_seconds"] == 360
    assert station["walk_maps_url"].startswith("https://www.google.com/maps/dir/?api=1")
    assert "travelmode=walking" in station["walk_maps_url"]


def test_get_commute_no_maps_url_when_listing_has_no_latlon(client, listing_id):
    resp = client.get(f"/api/listings/{listing_id}/commute")
    station = resp.json()["stations"][0]
    assert station["walk_maps_url"] is None


def test_get_commute_excludes_station_with_walk_over_30_minutes(client, listing_id):
    from app.commute.walk_store import replace_walk_distances

    replace_walk_distances(listing_id, [{"crs": "CLJ", "distance_meters": 2500, "duration_seconds": 1801}])
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert resp.json()["stations"] == []


def test_get_commute_includes_station_with_walk_at_exactly_30_minutes(client, listing_id, monkeypatch):
    from app.commute.walk_store import replace_walk_distances
    from app.routes import commute as commute_route

    monkeypatch.setattr(commute_route, "fetch_station_termini", lambda crs: {"crs": crs})
    replace_walk_distances(listing_id, [{"crs": "CLJ", "distance_meters": 2400, "duration_seconds": 1800}])
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert [s["crs"] for s in resp.json()["stations"]] == ["CLJ"]


def test_get_commute_falls_back_to_raw_distance_when_no_walk_data_and_within_half_mile(client, listing_id, monkeypatch):
    from app.routes import commute as commute_route

    monkeypatch.setattr(commute_route, "fetch_station_termini", lambda crs: {"crs": crs})
    # listing_id's only station (CLJ) is at raw distance 0.4mi, no stored walk data.
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert [s["crs"] for s in resp.json()["stations"]] == ["CLJ"]


def test_get_commute_excludes_station_beyond_half_mile_fallback_with_no_walk_data(client):
    store.create_stub_listing(3, "https://www.rightmove.co.uk/properties/3")
    store.apply_extracted_fields(
        3,
        {
            "nearest_stations_raw": json.dumps(
                [{"name": "Guildford Station", "distance": 0.9, "types": ["NATIONAL_TRAIN"]}]
            )
        },
    )
    resp = client.get("/api/listings/3/commute")
    assert resp.json()["stations"] == []


def test_get_commute_includes_station_at_exactly_half_mile_fallback_boundary(client, monkeypatch):
    from app.routes import commute as commute_route

    monkeypatch.setattr(commute_route, "fetch_station_termini", lambda crs: {"crs": crs})
    store.create_stub_listing(4, "https://www.rightmove.co.uk/properties/4")
    store.apply_extracted_fields(
        4,
        {
            "nearest_stations_raw": json.dumps(
                [{"name": "Guildford Station", "distance": 0.5, "types": ["NATIONAL_TRAIN"]}]
            )
        },
    )
    resp = client.get("/api/listings/4/commute")
    assert [s["crs"] for s in resp.json()["stations"]] == ["GLD"]


# --- walking API client ----------------------------------------------------

def test_compute_walk_distance_raises_clearly_when_key_unset(monkeypatch):
    from app.commute import walking

    monkeypatch.setattr(walking, "GOOGLE_MAPS_API_KEY", None)
    with pytest.raises(walking.WalkingApiError, match="GOOGLE_MAPS_API_KEY"):
        walking.compute_walk_distance(51.0, -0.1, 51.1, -0.2)


def test_compute_walk_distance_parses_success_response(monkeypatch):
    from app.commute import walking

    monkeypatch.setattr(walking, "GOOGLE_MAPS_API_KEY", "fake-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"routes": [{"duration": "360s", "distanceMeters": 500}]}).encode()

    monkeypatch.setattr(walking, "urlopen", lambda req, timeout: FakeResponse())
    result = walking.compute_walk_distance(51.0, -0.1, 51.1, -0.2)
    assert result == {"distance_meters": 500, "duration_seconds": 360}


def test_compute_walk_distance_handles_fractional_seconds(monkeypatch):
    from app.commute import walking

    monkeypatch.setattr(walking, "GOOGLE_MAPS_API_KEY", "fake-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"routes": [{"duration": "360.7s", "distanceMeters": 500}]}).encode()

    monkeypatch.setattr(walking, "urlopen", lambda req, timeout: FakeResponse())
    result = walking.compute_walk_distance(51.0, -0.1, 51.1, -0.2)
    assert result == {"distance_meters": 500, "duration_seconds": 360}


def test_compute_walk_distance_raises_walking_error_on_unparseable_duration(monkeypatch):
    from app.commute import walking

    monkeypatch.setattr(walking, "GOOGLE_MAPS_API_KEY", "fake-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"routes": [{"duration": "not-a-duration", "distanceMeters": 500}]}).encode()

    monkeypatch.setattr(walking, "urlopen", lambda req, timeout: FakeResponse())
    with pytest.raises(walking.WalkingApiError, match="unparseable"):
        walking.compute_walk_distance(51.0, -0.1, 51.1, -0.2)


def test_compute_walk_distance_raises_when_no_routes_returned(monkeypatch):
    from app.commute import walking

    monkeypatch.setattr(walking, "GOOGLE_MAPS_API_KEY", "fake-key")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"routes": []}).encode()

    monkeypatch.setattr(walking, "urlopen", lambda req, timeout: FakeResponse())
    with pytest.raises(walking.WalkingApiError, match="no route"):
        walking.compute_walk_distance(51.0, -0.1, 51.1, -0.2)


# --- walk_store --------------------------------------------------------

def test_replace_walk_distances_deletes_and_reinserts(client, listing_id):
    from app.commute.walk_store import get_walk_distances, replace_walk_distances

    replace_walk_distances(listing_id, [{"crs": "CLJ", "distance_meters": 500, "duration_seconds": 360}])
    assert get_walk_distances(listing_id) == {"CLJ": {"distance_meters": 500, "duration_seconds": 360}}

    replace_walk_distances(listing_id, [{"crs": "WAT", "distance_meters": 800, "duration_seconds": 600}])
    assert get_walk_distances(listing_id) == {"WAT": {"distance_meters": 800, "duration_seconds": 600}}


# --- station lat/long lookup ------------------------------------------

def test_latlong_for_crs_returns_coordinates():
    from app.commute.stations import latlong_for_crs

    lat, lon = latlong_for_crs("CLJ")
    assert lat != 0 and lon != 0


def test_latlong_for_crs_returns_none_for_unknown_crs():
    from app.commute.stations import latlong_for_crs

    assert latlong_for_crs("ZZZ") is None


def test_crs_for_name_strips_suffix_and_resolves():
    from app.commute.stations import crs_for_name

    assert crs_for_name("Clapham Junction Station") == "CLJ"


def test_crs_for_name_returns_none_for_unresolvable_name():
    from app.commute.stations import crs_for_name

    assert crs_for_name("Not A Real Station") is None


def test_crs_for_name_normalizes_period():
    from app.commute.stations import crs_for_name

    assert crs_for_name("St. Helier Station") == "SIH"


# --- nearest_stations_raw walk-data attachment (GET /api/listings/{id}) ----

def test_get_listing_attaches_walk_data_to_nearest_stations(client):
    from app.commute.walk_store import replace_walk_distances

    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(
        1,
        {
            "nearest_stations_raw": json.dumps(
                [
                    {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
                    {"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]},
                ]
            )
        },
    )
    replace_walk_distances(1, [{"crs": "CLJ", "distance_meters": 500, "duration_seconds": 360}])

    resp = client.get("/api/listings/1")
    nearest = resp.json()["nearest_stations_raw"]
    assert nearest[0]["walk_distance_meters"] == 500
    assert nearest[0]["walk_duration_seconds"] == 360
    assert nearest[1]["walk_distance_meters"] is None
    assert nearest[1]["walk_duration_seconds"] is None


def test_get_listing_nearest_stations_walk_data_none_when_nothing_stored(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(
        1,
        {
            "nearest_stations_raw": json.dumps(
                [{"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]}]
            )
        },
    )
    resp = client.get("/api/listings/1")
    nearest = resp.json()["nearest_stations_raw"]
    assert nearest[0]["walk_distance_meters"] is None
    assert nearest[0]["walk_duration_seconds"] is None


# --- station search (issue #28's destination typeahead) --------------------

def test_search_stations_matches_by_name():
    results = search_stations("padding")
    assert any(s["crs"] == "PAD" for s in results)


def test_search_stations_matches_by_crs_code():
    results = search_stations("pad")
    assert results[0]["crs"] == "PAD"


def test_search_stations_crs_exact_match_ranks_above_name_substring():
    # "wat" is both Waterloo's/Watford's name-prefix AND could substring-
    # match some other station's name -- an exact CRS match for a genuine
    # 3-letter code should still win outright over any name-based match.
    results = search_stations("wat")
    # Every CRS/name-prefix match for "wat" ranks above a merely-contains
    # match -- Watford Junction (name-prefix) should appear before a
    # station that only contains "wat" somewhere mid-name, if any exist.
    assert results[0]["name"].lower().startswith("wat") or results[0]["crs"].lower().startswith("wat")


def test_search_stations_blank_query_returns_empty():
    assert search_stations("") == []


def test_search_stations_respects_limit():
    results = search_stations("st", limit=3)
    assert len(results) <= 3
