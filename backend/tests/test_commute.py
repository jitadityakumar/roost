import json

import pytest

from app.commute.stations import resolve_crs_codes
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


def test_resolve_includes_all_stations_within_half_a_mile():
    stations = [
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
        {"name": "Woking Station", "distance": 0.2, "types": ["NATIONAL_TRAIN"]},
        {"name": "Barnes Station", "distance": 0.5, "types": ["NATIONAL_TRAIN"]},
    ]
    resolved = resolve_crs_codes(stations)
    assert {r["crs"] for r in resolved} == {"CLJ", "WOK", "BNS"}


def test_resolve_excludes_stations_beyond_half_a_mile():
    stations = [
        {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
        {"name": "Guildford Station", "distance": 0.51, "types": ["NATIONAL_TRAIN"]},
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
