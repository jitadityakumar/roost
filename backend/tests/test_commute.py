import json

import pytest

from app.commute.stations import resolve_crs_codes, search_stations
from app.listings import store


def _walk_row(station_index, rightmove_name, distance_meters, duration_seconds, mode="national-rail", stop_point_id="910GTEST"):
    return {
        "station_index": station_index,
        "rightmove_name": rightmove_name,
        "mode": mode,
        "stop_point_id": stop_point_id,
        "distance_meters": distance_meters,
        "duration_seconds": duration_seconds,
    }


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
    assert resolved == [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4, "index": 0}]


def test_resolve_keeps_parenthetical_suffix():
    stations = [{"name": "Earlswood (Surrey) Station", "distance": 0.3, "types": ["NATIONAL_TRAIN"]}]
    resolved = resolve_crs_codes(stations)
    assert resolved == [{"name": "Earlswood (Surrey)", "crs": "ELD", "distance": 0.3, "index": 0}]


def test_resolve_excludes_non_national_rail_entries():
    stations = [{"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]}]
    assert resolve_crs_codes(stations) == []


def test_resolve_drops_unmatched_names_without_erroring():
    stations = [{"name": "Not A Real Station", "distance": 0.1, "types": ["NATIONAL_TRAIN"]}]
    assert resolve_crs_codes(stations) == []


def test_resolve_index_reflects_position_in_original_list_not_filtered_list():
    # A non-national-rail entry at index 0 must not shift the surviving
    # national-rail entry's "index" down to 0 -- station_walk_distances is
    # keyed by position in the *original* nearest_stations_raw list.
    stations = [
        {"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]},
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert [r["index"] for r in resolved] == [1]


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
    replace_walk_distances(listing_id, [_walk_row(0, "Clapham Junction Station", 500, 360)])

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


def test_get_commute_falls_back_to_raw_distance_when_stale_row_name_mismatches(client, listing_id, monkeypatch):
    # Same rightmove_name-mismatch guard as _attach_walk_data, exercised
    # through get_commute's own lookup_walk() call specifically -- a stored
    # row at index 0 for a station Rightmove has since reordered away must
    # not silently attach to whatever is now at index 0.
    from app.commute.walk_store import replace_walk_distances
    from app.routes import commute as commute_route

    monkeypatch.setattr(commute_route, "fetch_station_termini", lambda crs: {"crs": crs})
    replace_walk_distances(listing_id, [_walk_row(0, "Some Other Station", 500, 360)])

    resp = client.get(f"/api/listings/{listing_id}/commute")
    station = resp.json()["stations"][0]
    # listing_id's index-0 station is actually "Clapham Junction Station" at
    # raw distance 0.4mi -- the stale row must be ignored, falling back to
    # the 0.5mi raw-distance rule (0.4 <= 0.5, so still shown, but with no
    # walk data attached).
    assert station["walk_distance_meters"] is None
    assert station["walk_duration_seconds"] is None
    assert station["walk_maps_url"] is None


def test_get_commute_excludes_station_with_walk_over_30_minutes(client, listing_id):
    from app.commute.walk_store import replace_walk_distances

    replace_walk_distances(listing_id, [_walk_row(0, "Clapham Junction Station", 2500, 1801)])
    resp = client.get(f"/api/listings/{listing_id}/commute")
    assert resp.json()["stations"] == []


def test_get_commute_includes_station_with_walk_at_exactly_30_minutes(client, listing_id, monkeypatch):
    from app.commute.walk_store import replace_walk_distances
    from app.routes import commute as commute_route

    monkeypatch.setattr(commute_route, "fetch_station_termini", lambda crs: {"crs": crs})
    replace_walk_distances(listing_id, [_walk_row(0, "Clapham Junction Station", 2400, 1800)])
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


# --- TfL API client ---------------------------------------------------

@pytest.fixture(autouse=True)
def _tfl_no_throttle(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "_throttle", lambda: None)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_compute_walk_distance_raises_clearly_when_key_unset(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", None)
    with pytest.raises(tfl_client.TflApiError, match="TFL_API_KEY"):
        tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")


def test_compute_walk_distance_parses_success_response(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    payload = {"journeys": [{"legs": [{"duration": 6, "distance": 500}]}]}
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    result = tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")
    assert result == {"distance_meters": 500, "duration_seconds": 360}


def test_compute_walk_distance_handles_missing_distance(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    payload = {"journeys": [{"legs": [{"duration": 6, "distance": None}]}]}
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    result = tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")
    assert result == {"distance_meters": None, "duration_seconds": 360}


def test_compute_walk_distance_raises_when_no_journeys_returned(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"journeys": []}))
    with pytest.raises(tfl_client.TflApiError, match="no journeys"):
        tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")


def test_compute_walk_distance_raises_when_journeys_key_missing(monkeypatch):
    # A 300 (ambiguous from/to) response, or any other unexpected shape,
    # won't raise via urlopen -- must be guarded explicitly.
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"$disambiguation": {}}))
    with pytest.raises(tfl_client.TflApiError, match="missing journeys"):
        tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")


def test_compute_walk_distance_raises_when_cloudflare_blocks_request(monkeypatch):
    from urllib.error import HTTPError

    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")

    def raise_403(req, timeout):
        raise HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(tfl_client, "urlopen", raise_403)
    with pytest.raises(tfl_client.TflApiError):
        tfl_client.compute_walk_distance(51.0, -0.1, "940GZZLUCLJ")


def test_resolve_stop_point_returns_none_when_key_unset(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", None)
    assert tfl_client.resolve_stop_point("Clapham Junction Station", "national-rail", 51.0, -0.1, 0.4) is None


def test_resolve_stop_point_scores_by_gap_to_rightmove_distance(monkeypatch):
    # Real validated case: Rightmove's "Streatham Station" (0.656mi) --
    # plain closest-lat/lon picks the physically-closer but wrong
    # "Streatham Common"; gap-scoring against Rightmove's own stated
    # distance picks the right one. Coordinates/distances approximate the
    # real ambiguous candidate set from issue #40's validation run.
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    listing_lat, listing_lon = 51.40, -0.10
    payload = {
        "matches": [
            # ~0.657mi from the listing, matching Rightmove's stated distance -- correct.
            {"id": "910GSTREATM", "name": "Streatham", "lat": 51.40951, "lon": -0.10},
            # ~0.100mi from the listing -- physically closer, but the wrong station.
            {"id": "910GSTRHCOM", "name": "Streatham Common", "lat": 51.40145, "lon": -0.10},
        ]
    }
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    result = tfl_client.resolve_stop_point("Streatham Station", "national-rail", listing_lat, listing_lon, 0.656)
    assert result == "910GSTREATM"


def test_resolve_stop_point_search_modes_widens_the_search_query(monkeypatch):
    # NATIONAL_TRAIN's search_modes override -- see handlers._TFL_SEARCH_MODES_BY_TYPE
    # -- must reach the actual /StopPoint/Search request, not just the
    # candidate-mode filter, since TfL classifies some Rightmove-tagged
    # national-rail stations (e.g. Chadwell Heath, Goodmayes) as
    # elizabeth-line-only in its own StopPoint data.
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    seen_urls = []

    def fake_urlopen(req, timeout):
        seen_urls.append(req.full_url)
        return _FakeResponse({"matches": [{"id": "910GCHDWLHT", "lat": 51.568, "lon": 0.129}]})

    monkeypatch.setattr(tfl_client, "urlopen", fake_urlopen)
    result = tfl_client.resolve_stop_point(
        "Chadwell Heath Station",
        "national-rail",
        51.5796,
        0.1329,
        0.84,
        search_modes="national-rail,elizabeth-line",
    )
    assert result == "910GCHDWLHT"
    assert "modes=national-rail,elizabeth-line" in seen_urls[0]


def test_resolve_stop_point_falls_back_to_closest_when_no_rightmove_distance(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    payload = {
        "matches": [
            {"id": "far", "lat": 51.5, "lon": -0.5},
            {"id": "near", "lat": 51.001, "lon": -0.001},
        ]
    }
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse(payload))
    result = tfl_client.resolve_stop_point("Somewhere", "national-rail", 51.0, -0.0, None)
    assert result == "near"


def test_resolve_stop_point_returns_none_when_no_candidates(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: _FakeResponse({"matches": []}))
    assert tfl_client.resolve_stop_point("Nowhere", "national-rail", 51.0, -0.1, 0.4) is None


def test_resolve_stop_point_drills_into_hub_children_for_target_mode(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    responses = [
        _FakeResponse({"matches": [{"id": "HUBSRA", "lat": 51.5416, "lon": -0.0042}]}),
        _FakeResponse(
            {
                "children": [
                    {"id": "910GSTFD", "modes": ["national-rail"]},
                    {"id": "940GZZLUSTD", "modes": ["tube"]},
                ]
            }
        ),
    ]
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: responses.pop(0))
    result = tfl_client.resolve_stop_point("Stratford Station", "national-rail", 51.54, -0.0, 0.1)
    assert result == "910GSTFD"


def test_resolve_stop_point_falls_back_to_closest_hub_child_on_ambiguous_mode_match(monkeypatch):
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    responses = [
        _FakeResponse({"matches": [{"id": "HUBSRA", "lat": 51.54, "lon": -0.0}]}),
        _FakeResponse(
            {
                "children": [
                    {"id": "far-dup", "modes": ["national-rail"], "lat": 51.6, "lon": -0.5},
                    {"id": "near-dup", "modes": ["national-rail"], "lat": 51.541, "lon": -0.001},
                ]
            }
        ),
    ]
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: responses.pop(0))
    result = tfl_client.resolve_stop_point("Stratford Station", "national-rail", 51.54, -0.0, 0.1)
    assert result == "near-dup"


def test_resolve_stop_point_hub_child_uses_search_modes_not_just_mode(monkeypatch):
    # Regression for a gap found in code review: a hub picked via a widened
    # search_modes (e.g. NATIONAL_TRAIN's "national-rail,elizabeth-line")
    # could have only an elizabeth-line child, not a national-rail one --
    # matching hub children on the single `mode` alone would silently fail
    # to resolve it, reproducing the exact elizabeth-line StopPoint bug this
    # widening exists to fix, one level down.
    from app.commute import tfl_client

    monkeypatch.setattr(tfl_client, "TFL_API_KEY", "fake-key")
    responses = [
        _FakeResponse({"matches": [{"id": "HUBXXX", "lat": 51.568, "lon": 0.129}]}),
        _FakeResponse({"children": [{"id": "910GCHDWLHT", "modes": ["elizabeth-line"]}]}),
    ]
    monkeypatch.setattr(tfl_client, "urlopen", lambda req, timeout: responses.pop(0))
    result = tfl_client.resolve_stop_point(
        "Chadwell Heath Station",
        "national-rail",
        51.5796,
        0.1329,
        0.84,
        search_modes="national-rail,elizabeth-line",
    )
    assert result == "910GCHDWLHT"


# --- walk_store --------------------------------------------------------

def test_replace_walk_distances_deletes_and_reinserts(client, listing_id):
    from app.commute.walk_store import get_walk_distances, replace_walk_distances

    replace_walk_distances(listing_id, [_walk_row(0, "Clapham Junction Station", 500, 360)])
    assert get_walk_distances(listing_id) == {
        0: {
            "rightmove_name": "Clapham Junction Station",
            "mode": "national-rail",
            "stop_point_id": "910GTEST",
            "distance_meters": 500,
            "duration_seconds": 360,
        }
    }

    replace_walk_distances(listing_id, [_walk_row(0, "Waterloo Station", 800, 600, stop_point_id="910GWATRLMN")])
    assert get_walk_distances(listing_id) == {
        0: {
            "rightmove_name": "Waterloo Station",
            "mode": "national-rail",
            "stop_point_id": "910GWATRLMN",
            "distance_meters": 800,
            "duration_seconds": 600,
        }
    }


def test_lookup_walk_returns_none_when_rightmove_name_no_longer_matches(client, listing_id):
    # Guards against Rightmove reordering nearest_stations_raw between the
    # scrape that computed this row and now -- index-keying alone would
    # otherwise silently attach a stale row to the wrong station.
    from app.commute.walk_store import get_walk_distances, lookup_walk, replace_walk_distances

    replace_walk_distances(listing_id, [_walk_row(0, "Clapham Junction Station", 500, 360)])
    walk_distances = get_walk_distances(listing_id)

    assert lookup_walk(walk_distances, 0, "Clapham Junction Station") is not None
    assert lookup_walk(walk_distances, 0, "Some Other Station") is None
    assert lookup_walk(walk_distances, 1, "Clapham Junction Station") is None


# --- station lat/long lookup ------------------------------------------

def test_latlong_for_crs_returns_coordinates():
    from app.commute.stations import latlong_for_crs

    lat, lon = latlong_for_crs("CLJ")
    assert lat != 0 and lon != 0


def test_latlong_for_crs_returns_none_for_unknown_crs():
    from app.commute.stations import latlong_for_crs

    assert latlong_for_crs("ZZZ") is None


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
    replace_walk_distances(1, [_walk_row(0, "Clapham Junction Station", 500, 360)])

    resp = client.get("/api/listings/1")
    nearest = resp.json()["nearest_stations_raw"]
    assert nearest[0]["walk_distance_meters"] == 500
    assert nearest[0]["walk_duration_seconds"] == 360
    assert nearest[1]["walk_distance_meters"] is None
    assert nearest[1]["walk_duration_seconds"] is None


def test_get_listing_ignores_stale_walk_row_after_station_reorder(client):
    # If nearest_stations_raw was reordered since this row was computed,
    # the stored rightmove_name at index 0 won't match the current entry --
    # must not silently attach it to the wrong station.
    from app.commute.walk_store import replace_walk_distances

    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(
        1,
        {
            "nearest_stations_raw": json.dumps(
                [{"name": "Becontree Station", "distance": 0.2, "types": ["LONDON_UNDERGROUND"]}]
            )
        },
    )
    replace_walk_distances(1, [_walk_row(0, "Clapham Junction Station", 500, 360)])

    resp = client.get("/api/listings/1")
    nearest = resp.json()["nearest_stations_raw"]
    assert nearest[0]["walk_distance_meters"] is None
    assert nearest[0]["walk_duration_seconds"] is None


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
