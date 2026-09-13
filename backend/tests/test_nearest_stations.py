import pytest

from app.commute.tfl_client import TflApiError
from app.listings import store
from app.nearest_stations import discovery, store as nearest_stations_store


@pytest.fixture
def listing_id():
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def _raw_stop_point(id_, name, modes, distance_meters, lat=51.4, lon=-0.2):
    return {"id": id_, "name": name, "modes": modes, "lat": lat, "lon": lon, "distance_meters": distance_meters}


# --- discover_candidates: grouping/dedup ------------------------------------

def test_discover_candidates_groups_same_station_across_modes(monkeypatch):
    # Wimbledon live-sample case (issue #92): 3 separate StopPoints for one
    # physical station must collapse to a single candidate. Real TfL
    # commonName values use the *fuller* "<Mode> Station" form (confirmed
    # live, and matching tfl_client.py's own _strip_suffix fixtures, e.g.
    # "Woking Rail Station") -- a bare "Wimbledon Rail"/"Wimbledon
    # Underground" (no "Station") would NOT exercise the real suffix-
    # stripping path, so use the realistic form here.
    monkeypatch.setattr(
        discovery,
        "search_stop_points_by_radius",
        lambda *a, **k: [
            _raw_stop_point("910GWMBLDN", "Wimbledon Rail Station", ["national-rail"], 150),
            _raw_stop_point("9400ZZLUWIM", "Wimbledon Underground Station", ["tube"], 140),
            _raw_stop_point("9400ZZLUWIM2", "Wimbledon Tram Stop", ["tram"], 160),
        ],
    )

    candidates = discovery.discover_candidates(51.42, -0.2)

    assert len(candidates) == 1
    c = candidates[0]
    # Nearest raw distance within the group wins as canonical.
    assert c["stop_point_id"] == "9400ZZLUWIM"
    assert c["distance_meters"] == 140
    assert set(c["modes"]) == {"national-rail", "tube", "tram"}


def test_discover_candidates_rounds_float_distance_to_int(monkeypatch):
    # TfL's radius search returns a float `distance` -- must be rounded to
    # match compute_walk_distance's own convention (and the INTEGER column
    # this ends up in), not stored as a raw float.
    monkeypatch.setattr(
        discovery,
        "search_stop_points_by_radius",
        lambda *a, **k: [_raw_stop_point("A", "Somewhere Rail Station", ["national-rail"], 120.7)],
    )

    candidates = discovery.discover_candidates(51.42, -0.2)
    assert candidates[0]["distance_meters"] == 121
    assert isinstance(candidates[0]["distance_meters"], int)


def test_discover_candidates_keeps_distinct_stations_separate(monkeypatch):
    monkeypatch.setattr(
        discovery,
        "search_stop_points_by_radius",
        lambda *a, **k: [
            _raw_stop_point("A", "Haydons Road", ["national-rail"], 500),
            _raw_stop_point("B", "Earlsfield", ["national-rail"], 900),
        ],
    )

    candidates = discovery.discover_candidates(51.42, -0.2)
    assert {c["name"] for c in candidates} == {"Haydons Road", "Earlsfield"}


def test_discover_candidates_returns_empty_on_no_raw_results(monkeypatch):
    monkeypatch.setattr(discovery, "search_stop_points_by_radius", lambda *a, **k: [])
    assert discovery.discover_candidates(51.42, -0.2) == []


# --- compute_nearest_stations ------------------------------------------------

def test_compute_nearest_stations_skips_when_latlon_missing(listing_id, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("discover_candidates should not be called without lat/lon")

    monkeypatch.setattr(discovery, "discover_candidates", boom)
    discovery.compute_nearest_stations(listing_id, None, None)  # should not raise


def test_compute_nearest_stations_does_not_wipe_existing_rows_on_discovery_failure(listing_id, monkeypatch):
    nearest_stations_store.replace_candidates(
        listing_id,
        [
            {
                "stop_point_id": "EXISTING",
                "name": "Existing Parkway",
                "modes": "national-rail",
                "lat": 51.4,
                "lon": -0.2,
                "distance_meters": 400,
                "walk_distance_meters": 400,
                "duration_seconds": 300,
                "computed_at": "2026-09-13T00:00:00+00:00",
            }
        ],
    )

    def raise_error(*a, **k):
        raise RuntimeError("TfL radius search blew up")

    monkeypatch.setattr(discovery, "discover_candidates", raise_error)

    discovery.compute_nearest_stations(listing_id, 51.4, -0.2)  # should not raise

    stations = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2, max_walk_minutes=999)
    assert len(stations) == 1
    assert stations[0]["name"] == "Existing Parkway"


def test_compute_nearest_stations_stores_null_duration_when_walk_call_fails(listing_id, monkeypatch):
    monkeypatch.setattr(
        discovery,
        "discover_candidates",
        lambda *a, **k: [
            {
                "stop_point_id": "A",
                "name": "Some Station",
                "modes": ["national-rail"],
                "lat": 51.41,
                "lon": -0.21,
                "distance_meters": 300,
            }
        ],
    )

    def raise_error(*a, **k):
        raise TflApiError("no journey found")

    monkeypatch.setattr(discovery, "compute_walk_distance", raise_error)

    discovery.compute_nearest_stations(listing_id, 51.4, -0.2)

    # Stored with NULL duration -- not dropped, per the plan's never-abort
    # contract for a per-candidate walk-duration failure.
    all_stations = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2, max_walk_minutes=999999)
    assert all_stations == []  # filtered out by get_nearest_stations (NULL duration)


def test_compute_nearest_stations_stores_full_deduped_set_unfiltered(listing_id, monkeypatch):
    # Stored rows aren't pre-filtered to MAX_WALK_MINUTES -- a future
    # threshold change only needs a re-read, not recomputation.
    monkeypatch.setattr(
        discovery,
        "discover_candidates",
        lambda *a, **k: [
            {
                "stop_point_id": "FAR",
                "name": "Far Away Station",
                "modes": ["national-rail"],
                "lat": 51.5,
                "lon": -0.3,
                "distance_meters": 1990,
            }
        ],
    )
    monkeypatch.setattr(
        discovery, "compute_walk_distance", lambda *a, **k: {"distance_meters": 1900, "duration_seconds": 2400}
    )

    discovery.compute_nearest_stations(listing_id, 51.4, -0.2)

    filtered = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2)
    assert filtered == []  # 40min > MAX_WALK_MINUTES (25)

    unfiltered = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2, max_walk_minutes=999)
    assert len(unfiltered) == 1


# --- store.get_nearest_stations ---------------------------------------------

def test_get_nearest_stations_filters_and_sorts_by_duration(listing_id):
    nearest_stations_store.replace_candidates(
        listing_id,
        [
            {
                "stop_point_id": "SLOW",
                "name": "Slow Parkway",
                "modes": "national-rail",
                "lat": 51.4,
                "lon": -0.2,
                "distance_meters": 1000,
                "walk_distance_meters": 1000,
                "duration_seconds": 1200,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
            {
                "stop_point_id": "FAST",
                "name": "Fast Parkway",
                "modes": "tube",
                "lat": 51.41,
                "lon": -0.21,
                "distance_meters": 300,
                "walk_distance_meters": 300,
                "duration_seconds": 300,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
            {
                "stop_point_id": "NODATA",
                "name": "No Duration Parkway",
                "modes": "tube",
                "lat": None,
                "lon": None,
                "distance_meters": 500,
                "walk_distance_meters": None,
                "duration_seconds": None,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
        ],
    )

    result = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2)

    assert [s["name"] for s in result] == ["Fast Parkway", "Slow Parkway"]
    assert result[0]["types"] == ["LONDON_UNDERGROUND"]
    assert result[0]["walk_maps_url"] is not None
    assert result[1]["types"] == ["NATIONAL_TRAIN"]


def test_get_nearest_stations_strips_mode_suffix_from_display_name(listing_id):
    # Type badge already conveys mode -- "Haydons Road Rail Station" should
    # render as just "Haydons Road", matching tfl_client's own suffix list
    # (Rail Station/Underground Station/DLR Station/Overground Station/
    # Tram Stop/bare Station).
    nearest_stations_store.replace_candidates(
        listing_id,
        [
            {
                "stop_point_id": "A",
                "name": "Haydons Road Rail Station",
                "modes": "national-rail",
                "lat": 51.4,
                "lon": -0.2,
                "distance_meters": 300,
                "walk_distance_meters": 300,
                "duration_seconds": 300,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
            {
                "stop_point_id": "B",
                "name": "Colliers Wood Underground Station",
                "modes": "tube",
                "lat": 51.41,
                "lon": -0.21,
                "distance_meters": 400,
                "walk_distance_meters": 400,
                "duration_seconds": 400,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
            {
                "stop_point_id": "C",
                "name": "Wimbledon Tram Stop",
                "modes": "tram",
                "lat": 51.42,
                "lon": -0.22,
                "distance_meters": 500,
                "walk_distance_meters": 500,
                "duration_seconds": 500,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
        ],
    )

    result = nearest_stations_store.get_nearest_stations(listing_id, 51.4, -0.2)

    assert {s["name"] for s in result} == {"Haydons Road", "Colliers Wood", "Wimbledon"}


def test_get_nearest_stations_no_walk_maps_url_without_origin(listing_id):
    nearest_stations_store.replace_candidates(
        listing_id,
        [
            {
                "stop_point_id": "A",
                "name": "Station A",
                "modes": "national-rail",
                "lat": 51.4,
                "lon": -0.2,
                "distance_meters": 300,
                "walk_distance_meters": 300,
                "duration_seconds": 300,
                "computed_at": "2026-09-13T00:00:00+00:00",
            },
        ],
    )

    result = nearest_stations_store.get_nearest_stations(listing_id, None, None)
    assert result[0]["walk_maps_url"] is None


# --- modes_to_rightmove_types ------------------------------------------------

def test_modes_to_rightmove_types_translates_and_dedupes_preserving_order():
    from app.nearest_stations.modes import modes_to_rightmove_types

    result = modes_to_rightmove_types(["tube", "national-rail", "tube"])
    assert result == ["LONDON_UNDERGROUND", "NATIONAL_TRAIN"]


def test_modes_to_rightmove_types_drops_unmapped_modes():
    from app.nearest_stations.modes import modes_to_rightmove_types

    assert modes_to_rightmove_types(["bus", "tube"]) == ["LONDON_UNDERGROUND"]
    assert modes_to_rightmove_types(["river-bus"]) == []
