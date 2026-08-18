import pytest

from app.destinations import journey_store, store
from app.listings import store as listings_store

LAT, LON = 51.319, -0.559


@pytest.fixture(autouse=True)
def listing():
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"latitude": LAT, "longitude": LON})


def _row(destination_id, duration_minutes=24):
    return {
        "destination_id": destination_id,
        "duration_minutes": duration_minutes,
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


def _pool(to_identifier="910GPADTON"):
    return {
        "query_params": {
            "journeyPreference": "LeastInterchange",
            "mode": "national-rail",
            "date": "20260824",
            "time": "0830",
            "to_identifier": to_identifier,
        },
        "candidate_pool": [{"startDateTime": "2026-08-17T08:40:00", "duration": 24, "legs": []}],
    }


def _create_destination():
    return store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")


# --- replace_journeys -----------------------------------------------------

def test_replace_journeys_writes_both_tables():
    d = _create_destination()
    journey_store.replace_journeys(1, [(_row(d["id"]), _pool())])

    assert journey_store.get_journeys(1)[d["id"]]["duration_minutes"] == 24
    pool_ids = journey_store.get_scan_pool_ids(1)
    assert d["id"] in pool_ids
    pool = journey_store.get_scan_pool(pool_ids[d["id"]])
    assert pool["query_params"]["to_identifier"] == "910GPADTON"
    assert len(pool["candidate_pool"]) == 1


def test_replace_journeys_row_without_pool_stores_no_pool_row():
    d = _create_destination()
    journey_store.replace_journeys(1, [(_row(d["id"]), None)])

    assert journey_store.get_journeys(1)[d["id"]]["duration_minutes"] == 24
    assert journey_store.get_scan_pool_ids(1) == {}


def test_replace_journeys_overwrites_not_appends():
    d = _create_destination()
    journey_store.replace_journeys(1, [(_row(d["id"]), _pool())])
    journey_store.replace_journeys(1, [(_row(d["id"], duration_minutes=30), _pool("910GNEWID"))])

    assert journey_store.get_journeys(1)[d["id"]]["duration_minutes"] == 30
    pool_ids = journey_store.get_scan_pool_ids(1)
    assert len(pool_ids) == 1
    pool = journey_store.get_scan_pool(pool_ids[d["id"]])
    assert pool["query_params"]["to_identifier"] == "910GNEWID"


def test_replace_journeys_clears_pool_for_destination_missing_from_entries():
    d = _create_destination()
    journey_store.replace_journeys(1, [(_row(d["id"]), _pool())])
    assert journey_store.get_scan_pool_ids(1) != {}

    journey_store.replace_journeys(1, [])

    assert journey_store.get_journeys(1) == {}
    assert journey_store.get_scan_pool_ids(1) == {}


# --- replace_single ---------------------------------------------------

def test_replace_single_writes_row_and_pool():
    d = _create_destination()
    journey_store.replace_single(1, d["id"], _row(d["id"]), _pool())

    assert journey_store.get_journeys(1)[d["id"]]["duration_minutes"] == 24
    pool_ids = journey_store.get_scan_pool_ids(1)
    assert d["id"] in pool_ids


def test_replace_single_none_row_clears_both_tables():
    d = _create_destination()
    journey_store.replace_single(1, d["id"], _row(d["id"]), _pool())
    assert journey_store.get_scan_pool_ids(1) != {}

    journey_store.replace_single(1, d["id"], None)

    assert journey_store.get_journeys(1) == {}
    assert journey_store.get_scan_pool_ids(1) == {}


def test_replace_single_none_row_never_stores_an_orphan_pool():
    # A pool row must never exist without its matching destination_journeys
    # row -- the UI has no way to link to it. Not reachable from any current
    # caller (compute.py always pairs row/pool together), but replace_single
    # itself should enforce the invariant rather than relying on callers.
    d = _create_destination()
    journey_store.replace_single(1, d["id"], None, _pool())

    assert journey_store.get_journeys(1) == {}
    assert journey_store.get_scan_pool_ids(1) == {}


def test_replace_single_leaves_other_destinations_pool_untouched():
    d1 = _create_destination()
    d2 = store.create_destination("Gym", "station", "910GOTHERID", "Other", 0, "08:30")
    journey_store.replace_single(1, d1["id"], _row(d1["id"]), _pool("910GPADTON"))
    journey_store.replace_single(1, d2["id"], _row(d2["id"]), _pool("910GOTHERID"))

    journey_store.replace_single(1, d1["id"], None)

    pool_ids = journey_store.get_scan_pool_ids(1)
    assert d1["id"] not in pool_ids
    assert d2["id"] in pool_ids


# --- delete_for_destination --------------------------------------------

def test_delete_for_destination_clears_pool_too():
    d = _create_destination()
    journey_store.replace_single(1, d["id"], _row(d["id"]), _pool())

    journey_store.delete_for_destination(1, d["id"])

    assert journey_store.get_journeys(1) == {}
    assert journey_store.get_scan_pool_ids(1) == {}


# --- get_scan_pool -------------------------------------------------------

def test_get_scan_pool_returns_none_for_missing_id():
    assert journey_store.get_scan_pool(999) is None


def test_get_scan_pool_round_trips_json_columns():
    d = _create_destination()
    journey_store.replace_single(1, d["id"], _row(d["id"]), _pool())
    pool_id = journey_store.get_scan_pool_ids(1)[d["id"]]

    pool = journey_store.get_scan_pool(pool_id)

    assert pool["destination_id"] == d["id"]
    assert pool["listing_id"] == 1
    assert isinstance(pool["query_params"], dict)
    assert isinstance(pool["candidate_pool"], list)
