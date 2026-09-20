from app.detail_sections.store import SECTION_KEYS

ALL_EXPANDED = {f"{key}_expanded": True for key in SECTION_KEYS}


def test_get_sections_config_seeded_defaults(client):
    resp = client.get("/api/admin/detail-page-sections")
    assert resp.status_code == 200
    body = resp.json()
    assert body["details_expanded"] is True
    assert body["epc_expanded"] is False
    assert body["room_sizes_expanded"] is False
    assert body["crime_expanded"] is False
    assert body["jobs_expanded"] is False
    assert body["local_politics_expanded"] is False


def test_put_sections_config_round_trips(client):
    resp = client.put("/api/admin/detail-page-sections", json=ALL_EXPANDED)
    assert resp.status_code == 200
    assert resp.json() == ALL_EXPANDED
    assert client.get("/api/admin/detail-page-sections").json() == ALL_EXPANDED


def test_put_sections_config_422_on_missing_key(client):
    incomplete = dict(ALL_EXPANDED)
    del incomplete["jobs_expanded"]
    resp = client.put("/api/admin/detail-page-sections", json=incomplete)
    assert resp.status_code == 422


def test_put_sections_config_422_on_unknown_key(client):
    bad = {**ALL_EXPANDED, "made_up_expanded": True}
    resp = client.put("/api/admin/detail-page-sections", json=bad)
    assert resp.status_code == 422


def test_put_sections_config_422_on_non_bool_value(client):
    bad = {**ALL_EXPANDED, "jobs_expanded": "not-a-bool"}
    resp = client.put("/api/admin/detail-page-sections", json=bad)
    assert resp.status_code == 422
