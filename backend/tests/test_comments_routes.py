from app.listings import store

VALID_URL = "https://www.rightmove.co.uk/properties/123456789"


def test_create_comment_returns_full_listing_with_comment(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.post("/api/listings/1/comments", json={"text": "Nice garden", "initials": "JK"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert len(body["comments"]) == 1
    assert body["comments"][0]["text"] == "Nice garden"
    assert body["comments"][0]["initials"] == "JK"
    assert body["comments"][0]["comment_type"] == "general"


def test_create_comment_422_on_blank_text(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.post("/api/listings/1/comments", json={"text": "   ", "initials": "JK"})
    assert resp.status_code == 422


def test_create_comment_422_on_blank_initials(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.post("/api/listings/1/comments", json={"text": "Nice garden", "initials": "   "})
    assert resp.status_code == 422


def test_create_comment_404_on_missing_listing(client):
    resp = client.post("/api/listings/999/comments", json={"text": "x", "initials": "JK"})
    assert resp.status_code == 404


def test_update_comment_happy_path(client):
    store.create_stub_listing(1, VALID_URL)
    create_resp = client.post("/api/listings/1/comments", json={"text": "Original", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]

    resp = client.patch(f"/api/listings/1/comments/{comment_id}", json={"text": "Edited", "initials": "AB"})
    assert resp.status_code == 200
    comment = resp.json()["comments"][0]
    assert comment["text"] == "Edited"
    assert comment["initials"] == "AB"


def test_update_comment_422_on_blank_text(client):
    store.create_stub_listing(1, VALID_URL)
    create_resp = client.post("/api/listings/1/comments", json={"text": "Original", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]
    resp = client.patch(f"/api/listings/1/comments/{comment_id}", json={"text": " ", "initials": "JK"})
    assert resp.status_code == 422


def test_update_comment_422_on_blank_initials(client):
    store.create_stub_listing(1, VALID_URL)
    create_resp = client.post("/api/listings/1/comments", json={"text": "Original", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]
    resp = client.patch(f"/api/listings/1/comments/{comment_id}", json={"text": "Edited", "initials": " "})
    assert resp.status_code == 422


def test_update_comment_404_on_missing_listing(client):
    resp = client.patch("/api/listings/999/comments/1", json={"text": "x", "initials": "JK"})
    assert resp.status_code == 404


def test_update_comment_404_on_unknown_comment_id(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1/comments/999", json={"text": "x", "initials": "JK"})
    assert resp.status_code == 404


def test_update_comment_404_on_listing_comment_id_mismatch(client):
    store.create_stub_listing(1, VALID_URL)
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    create_resp = client.post("/api/listings/1/comments", json={"text": "Original", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]

    resp = client.patch(f"/api/listings/2/comments/{comment_id}", json={"text": "x", "initials": "JK"})
    assert resp.status_code == 404


def test_delete_comment_happy_path(client):
    store.create_stub_listing(1, VALID_URL)
    create_resp = client.post("/api/listings/1/comments", json={"text": "Bye", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]

    resp = client.delete(f"/api/listings/1/comments/{comment_id}")
    assert resp.status_code == 200
    assert resp.json()["comments"] == []


def test_delete_comment_404_on_missing_listing(client):
    resp = client.delete("/api/listings/999/comments/1")
    assert resp.status_code == 404


def test_delete_comment_404_on_unknown_comment_id(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.delete("/api/listings/1/comments/999")
    assert resp.status_code == 404


def test_delete_comment_404_on_listing_comment_id_mismatch(client):
    store.create_stub_listing(1, VALID_URL)
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    create_resp = client.post("/api/listings/1/comments", json={"text": "Original", "initials": "JK"})
    comment_id = create_resp.json()["comments"][0]["id"]

    resp = client.delete(f"/api/listings/2/comments/{comment_id}")
    assert resp.status_code == 404
