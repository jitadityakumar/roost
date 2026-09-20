import json

import pytest

from app.crime.client import CrimeApiError
from app.jobs import handlers
from app.listings import store as listings_store
from app.localpolitics import control, members_client, service, store

URL = "https://www.rightmove.co.uk/properties/1"

CSV = (
    "id,council id,authority,year,total,con,lab,ld,green,ukip,ref,pc,snp,other,majority,\n"
    "1,249,Merton,2025,57,7,30,17,0,0,0,0,0,3,LAB,\n"
    '2,249,Merton,2026,57,4,32,19,0,0,0,0,0,2,LAB,E09000024\n'
    '3,900,"Nowhere, Borough",2026,40,10,10,10,0,0,10,0,0,0,NOC,E09000999\n'
    "4,901,No Gss Council,2026,30,10,10,10,0,0,0,0,0,0,NOC,\n"
)

MP = {
    "members_api_id": 4401,
    "member_id": 5321,
    "member_name": "Mr Paul Kohler MP",
    "party_name": "Liberal Democrat",
    "party_abbreviation": "LD",
    "party_colour": "#fc7d0b",
    "result": "LD Gain",
    "majority": 12610,
    "turnout": 54985,
    "electorate": 76334,
}

RESOLVED = {
    "admin_district": "Merton",
    "admin_ward": "Abbey",
    "parish": "Merton, unparished area",
    "admin_county": None,
    "parliamentary_constituency_2024": "Wimbledon",
    "codes": {
        "admin_district": "E09000024",
        "admin_ward": "E05013810",
        "parliamentary_constituency_2024": "E14001586",
    },
}


# --- CSV import / composition -------------------------------------------------


def test_import_council_csv_latest_year_with_previous(isolated_db):
    assert store.import_council_csv(CSV) == 2  # No Gss Council skipped

    merton = store.get_composition("E09000024")
    assert merton["authority"] == "Merton"
    assert merton["year"] == 2026
    assert merton["total"] == 57
    assert merton["parties"]["lab"] == 32
    assert merton["previous"] == {"year": 2025, "total": 57, "parties": {**merton["previous"]["parties"], "lab": 30}}
    assert merton["previous"]["parties"]["con"] == 7

    # quoted comma in the authority name parsed correctly; no prior-year row
    assert store.get_composition("E09000999")["authority"] == "Nowhere, Borough"
    assert store.get_composition("E09000999")["previous"] is None
    assert store.get_composition("E09000999")["parties"]["ref"] == 10


def test_import_council_csv_is_idempotent(isolated_db):
    store.import_council_csv(CSV)
    store.import_council_csv(CSV)
    assert store.get_composition("E09000024")["total"] == 57


def test_get_composition_none_for_unknown_or_missing_gss(isolated_db):
    assert store.get_composition("E0nope") is None
    assert store.get_composition(None) is None


# --- control headline / rows --------------------------------------------------

EMPTY = {k: 0 for k in store.PARTIES}


def test_headline_majority():
    h = control.headline(57, {**EMPTY, "lab": 32, "ld": 19, "con": 4, "other": 2})
    assert h == {"status": "majority", "party": "Labour", "seats": 32, "total": 57}


def test_headline_exactly_half_is_not_majority():
    h = control.headline(60, {**EMPTY, "lab": 30, "con": 30})
    assert h["status"] == "no_overall_majority"
    assert h["party"] is None  # exact tie -> no largest party named


def test_headline_no_overall_majority_names_largest():
    h = control.headline(70, {**EMPTY, "lab": 30, "con": 25, "ld": 15})
    assert h == {"status": "no_overall_majority", "party": "Labour", "seats": 30, "total": 70}


def test_majority_threshold():
    assert control.majority_threshold(57) == 29
    assert control.majority_threshold(60) == 31


def test_party_rows_sorted_with_change_and_hides_zero_zero():
    previous = {"year": 2025, "total": 57, "parties": {**EMPTY, "lab": 30, "ld": 17, "con": 7, "other": 3}}
    rows = control.party_rows(57, {**EMPTY, "lab": 32, "ld": 19, "con": 4, "other": 2}, previous)
    assert [r["key"] for r in rows] == ["lab", "ld", "con", "other"]
    assert rows[0] == {"key": "lab", "name": "Labour", "seats": 32, "share": 56, "previous_seats": 30, "change": 2}
    assert rows[2]["change"] == -3


def test_party_rows_keeps_party_that_lost_all_seats_and_none_change_without_previous():
    previous = {"year": 2025, "total": 10, "parties": {**EMPTY, "lab": 6, "con": 4}}
    rows = control.party_rows(10, {**EMPTY, "lab": 10}, previous)
    assert {r["key"]: r["change"] for r in rows} == {"lab": 4, "con": -4}
    rows = control.party_rows(10, {**EMPTY, "lab": 10}, None)
    assert rows[0]["change"] is None and rows[0]["previous_seats"] is None


# --- members client -----------------------------------------------------------


def _search_item(name="Wimbledon", end_date=None, member=True, colour="fc7d0b"):
    value = {"id": 4401, "name": name, "endDate": end_date, "currentRepresentation": {"member": None}}
    if member:
        value["currentRepresentation"]["member"] = {
            "value": {
                "id": 5321,
                "nameFullTitle": "Mr Paul Kohler MP",
                "latestParty": {"name": "Liberal Democrat", "abbreviation": "LD", "backgroundColour": colour},
            }
        }
    return {"value": value}


def _fake_get(items, results=None, results_error=False):
    def fake(path, params=None):
        if path.endswith("/Search"):
            return {"items": items}
        if results_error:
            raise members_client.MembersApiError("boom")
        return {"value": results if results is not None else []}

    return fake


ELECTION = [
    {"result": "Old", "isNotional": False, "isGeneralElection": True, "electionDate": "2019-12-12", "majority": 1},
    {
        "result": "LD Gain",
        "isNotional": False,
        "isGeneralElection": True,
        "electionDate": "2024-07-04",
        "majority": 12610,
        "turnout": 54985,
        "electorate": 76334,
    },
    {"result": "Notional", "isNotional": True, "isGeneralElection": True, "electionDate": "2025-01-01"},
]


def test_find_mp_exact_single_match(monkeypatch):
    monkeypatch.setattr(members_client, "_get", _fake_get([_search_item()], ELECTION))
    assert members_client.find_mp("Wimbledon") == MP


def test_find_mp_null_party_colour_stays_none(monkeypatch):
    monkeypatch.setattr(members_client, "_get", _fake_get([_search_item(colour=None)], ELECTION))
    assert members_client.find_mp("Wimbledon")["party_colour"] is None


@pytest.mark.parametrize(
    "items",
    [
        [],
        [_search_item("Richmond Park"), _search_item("Richmond (Yorks)")],  # no exact match
        [_search_item(), _search_item()],  # ambiguous exact
        [_search_item(end_date="2024-05-30T00:00:00")],  # abolished constituency
        [_search_item(member=False)],  # no sitting member
    ],
)
def test_find_mp_returns_none_unless_exactly_one_current_exact_match(monkeypatch, items):
    monkeypatch.setattr(members_client, "_get", _fake_get(items, ELECTION))
    assert members_client.find_mp("Wimbledon") is None


def test_find_mp_tolerates_election_results_failure(monkeypatch):
    monkeypatch.setattr(members_client, "_get", _fake_get([_search_item()], results_error=True))
    mp = members_client.find_mp("Wimbledon")
    assert mp["member_name"] == "Mr Paul Kohler MP"
    assert mp["majority"] is None and mp["result"] is None


def test_find_mp_propagates_search_failure(monkeypatch):
    def boom(path, params=None):
        raise members_client.MembersApiError("down")

    monkeypatch.setattr(members_client, "_get", boom)
    with pytest.raises(members_client.MembersApiError):
        members_client.find_mp("Wimbledon")


# --- service ------------------------------------------------------------------


def test_columns_from_resolved_maps_and_clears():
    cols = service.columns_from_resolved(RESOLVED)
    assert cols == {
        "admin_ward": "Abbey",
        "admin_ward_gss": "E05013810",
        "parish": "Merton, unparished area",
        "admin_county": None,
        "constituency": "Wimbledon",
        "constituency_gss": "E14001586",
    }
    assert set(service.columns_from_resolved(None).values()) == {None}
    # a council-only result (older callers/fakes) is tolerated
    assert service.columns_from_resolved({"admin_district": "X", "codes": {"admin_district": "E1"}})[
        "constituency_gss"
    ] is None


def test_ensure_mp_skips_without_constituency(isolated_db):
    assert service.ensure_mp(None, None) == "skipped"
    assert service.ensure_mp("E1", None) == "skipped"


def test_ensure_mp_stores_then_skips_existing_unless_forced(isolated_db, monkeypatch):
    calls = []
    monkeypatch.setattr(members_client, "find_mp", lambda name: calls.append(name) or MP)
    assert service.ensure_mp("E14001586", "Wimbledon") == "ok"
    assert store.get_mp("E14001586")["member_name"] == "Mr Paul Kohler MP"
    assert service.ensure_mp("E14001586", "Wimbledon") == "skipped"
    assert calls == ["Wimbledon"]
    assert service.ensure_mp("E14001586", "Wimbledon", force=True) == "ok"
    assert len(calls) == 2


def test_ensure_mp_never_raises_and_keeps_existing_row(isolated_db, monkeypatch):
    store.upsert_mp("E14001586", "Wimbledon", MP)

    def boom(name):
        raise members_client.MembersApiError("down")

    monkeypatch.setattr(members_client, "find_mp", boom)
    assert service.ensure_mp("E14001586", "Wimbledon", force=True) == "error"
    assert store.get_mp("E14001586")["member_name"] == "Mr Paul Kohler MP"

    monkeypatch.setattr(members_client, "find_mp", lambda name: None)
    assert service.ensure_mp("E14001586", "Wimbledon", force=True) == "not_found"
    assert store.get_mp("E14001586")["member_name"] == "Mr Paul Kohler MP"


# --- handler wiring -----------------------------------------------------------


def test_scrape_writes_politics_columns_and_resolves_mp(client, monkeypatch):
    listings_store.create_stub_listing(1, URL)
    monkeypatch.setattr(handlers, "lookup_postcode", lambda postcode: RESOLVED)
    monkeypatch.setattr(members_client, "find_mp", lambda name: MP)

    handlers.handle_rightmove_extract({"id": 1, "listing_id": 1, "skip_llm_chain": 1})

    listing = listings_store.get_listing(1)
    assert listing["admin_ward"] == "Abbey"
    assert listing["constituency_gss"] == "E14001586"
    assert store.get_mp("E14001586")["member_name"] == "Mr Paul Kohler MP"


def test_scrape_survives_members_api_outage(client, monkeypatch):
    listings_store.create_stub_listing(1, URL)
    monkeypatch.setattr(handlers, "lookup_postcode", lambda postcode: RESOLVED)

    def boom(name):
        raise members_client.MembersApiError("down")

    monkeypatch.setattr(members_client, "find_mp", boom)

    handlers.handle_rightmove_extract({"id": 1, "listing_id": 1, "skip_llm_chain": 1})

    listing = listings_store.get_listing(1)
    assert listing["extraction_status"] == "done"
    assert listing["constituency"] == "Wimbledon"
    assert store.get_mp("E14001586") is None


def test_scrape_clears_politics_columns_when_postcode_changes_and_unresolvable(client, monkeypatch):
    listings_store.create_stub_listing(1, URL)
    listings_store.apply_extracted_fields(1, {"postcode": "OLD 1AA", **service.columns_from_resolved(RESOLVED)})
    monkeypatch.setattr(handlers, "lookup_postcode", lambda postcode: None)

    handlers.handle_rightmove_extract({"id": 1, "listing_id": 1, "skip_llm_chain": 1})

    listing = listings_store.get_listing(1)
    assert listing["constituency_gss"] is None and listing["admin_ward"] is None


def test_patch_postcode_resolves_politics_fields_non_sticky(client, monkeypatch):
    from app.routes import listings as listings_route

    listings_store.create_stub_listing(1, URL)
    monkeypatch.setattr(listings_route, "lookup_postcode", lambda postcode: RESOLVED)
    monkeypatch.setattr(members_client, "find_mp", lambda name: MP)

    resp = client.patch("/api/listings/1", json={"fields": {"postcode": "SW19 3AA"}})
    body = resp.json()
    assert body["constituency"] == "Wimbledon"
    assert body["admin_ward"] == "Abbey"
    assert "constituency" not in body["edited_fields"]
    assert store.get_mp("E14001586") is not None


# --- routes -------------------------------------------------------------------


def _seed_listing(with_postcode=True):
    listings_store.create_stub_listing(1, URL)
    fields = {
        "admin_district": "Merton",
        "admin_district_gss": "E09000024",
        **service.columns_from_resolved(RESOLVED),
    }
    if with_postcode:
        fields["postcode"] = "SW19 3AA"
    listings_store.apply_extracted_fields(1, fields)


def test_get_local_politics_404(client):
    assert client.get("/api/listings/999/local-politics").status_code == 404


def test_get_local_politics_empty_listing(client):
    listings_store.create_stub_listing(1, URL)
    body = client.get("/api/listings/1/local-politics").json()
    assert body == {"mp": None, "council": None, "control": None, "has_data": False}


def test_get_local_politics_full(client):
    _seed_listing()
    store.import_council_csv(CSV)
    store.upsert_mp("E14001586", "Wimbledon", MP)

    body = client.get("/api/listings/1/local-politics").json()

    assert body["has_data"] is True
    assert body["council"] == {"name": "Merton", "county": None, "ward": "Abbey", "parish": "Merton, unparished area"}
    assert body["mp"]["name"] == "Mr Paul Kohler MP"
    assert body["mp"]["party_colour"] == "#fc7d0b"
    assert body["mp"]["turnout_pct"] == 72.0
    assert body["mp"]["thumbnail_url"].endswith("/Members/5321/Thumbnail")
    control_ = body["control"]
    assert control_["total"] == 57 and control_["majority_threshold"] == 29
    assert control_["headline"]["party"] == "Labour"
    assert control_["previous_year"] == 2025
    assert control_["parties"][0]["name"] == "Labour"


def test_get_local_politics_council_without_composition_row(client):
    _seed_listing()
    body = client.get("/api/listings/1/local-politics").json()
    assert body["council"]["name"] == "Merton"
    assert body["control"] is None and body["mp"] is None


def test_refresh_success_writes_fields_and_mp(client, monkeypatch):
    from app.routes import local_politics as route

    listings_store.create_stub_listing(1, URL)
    listings_store.apply_extracted_fields(1, {"postcode": "SW19 3AA"})
    monkeypatch.setattr(route, "lookup_postcode", lambda postcode: RESOLVED)
    monkeypatch.setattr(members_client, "find_mp", lambda name: MP)

    resp = client.post("/api/listings/1/local-politics/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["refresh"] == {"ok": True, "message": None}
    assert body["mp"]["name"] == "Mr Paul Kohler MP"
    assert body["council"]["ward"] == "Abbey"


def test_refresh_forces_mp_refetch(client, monkeypatch):
    from app.routes import local_politics as route

    _seed_listing()
    store.upsert_mp("E14001586", "Wimbledon", {**MP, "member_name": "Old MP"})
    monkeypatch.setattr(route, "lookup_postcode", lambda postcode: RESOLVED)
    monkeypatch.setattr(members_client, "find_mp", lambda name: MP)

    body = client.post("/api/listings/1/local-politics/refresh").json()
    assert body["mp"]["name"] == "Mr Paul Kohler MP"


def test_refresh_postcode_request_failure_is_502_and_keeps_data(client, monkeypatch):
    from app.routes import local_politics as route

    _seed_listing()

    def boom(postcode):
        raise CrimeApiError("down")

    monkeypatch.setattr(route, "lookup_postcode", boom)
    resp = client.post("/api/listings/1/local-politics/refresh")
    assert resp.status_code == 502
    assert listings_store.get_listing(1)["admin_ward"] == "Abbey"


def test_refresh_unrecognised_postcode_reports_and_keeps_data(client, monkeypatch):
    from app.routes import local_politics as route

    _seed_listing()
    monkeypatch.setattr(route, "lookup_postcode", lambda postcode: None)
    body = client.post("/api/listings/1/local-politics/refresh").json()
    assert body["refresh"]["ok"] is False
    assert body["council"]["ward"] == "Abbey"


@pytest.mark.parametrize("finder,expected", [("error", "request failed"), ("none", "single MP")])
def test_refresh_mp_failure_keeps_existing_mp_and_reports(client, monkeypatch, finder, expected):
    from app.routes import local_politics as route

    _seed_listing()
    store.upsert_mp("E14001586", "Wimbledon", MP)
    monkeypatch.setattr(route, "lookup_postcode", lambda postcode: RESOLVED)

    def boom(name):
        raise members_client.MembersApiError("down")

    monkeypatch.setattr(members_client, "find_mp", boom if finder == "error" else lambda name: None)

    body = client.post("/api/listings/1/local-politics/refresh").json()
    assert body["refresh"]["ok"] is False
    assert expected in body["refresh"]["message"]
    assert body["mp"]["name"] == "Mr Paul Kohler MP"


def test_refresh_404_and_no_postcode(client):
    assert client.post("/api/listings/999/local-politics/refresh").status_code == 404
    listings_store.create_stub_listing(1, URL)
    assert client.post("/api/listings/1/local-politics/refresh").status_code == 422
