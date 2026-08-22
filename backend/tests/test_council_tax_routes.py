def test_list_empty(client):
    resp = client.get("/api/council-tax")
    assert resp.status_code == 200
    assert resp.json() == []


def test_put_creates_and_get_returns_it(client):
    resp = client.put(
        "/api/council-tax/E00000001",
        json={"council_name": "Sampleton", "band_a": 1000, "band_d": 2340},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["council_name"] == "Sampleton"
    assert body["band_a"] == 1000
    assert body["band_d"] == 2340
    assert body["band_h"] is None

    listed = client.get("/api/council-tax").json()
    assert len(listed) == 1
    assert listed[0]["gss_code"] == "E00000001"


def test_put_is_a_full_replacement(client):
    client.put("/api/council-tax/E00000001", json={"council_name": "Sampleton", "band_a": 1000, "band_b": 1100})
    resp = client.put("/api/council-tax/E00000001", json={"council_name": "Sampleton", "band_a": 2000})
    assert resp.json()["band_a"] == 2000
    assert resp.json()["band_b"] is None


def test_put_rejects_blank_council_name(client):
    resp = client.put("/api/council-tax/E00000001", json={"council_name": "  "})
    assert resp.status_code == 422


def test_delete_removes_the_row(client):
    client.put("/api/council-tax/E00000001", json={"council_name": "Sampleton", "band_a": 1000})
    resp = client.delete("/api/council-tax/E00000001")
    assert resp.status_code == 204
    assert client.get("/api/council-tax").json() == []
