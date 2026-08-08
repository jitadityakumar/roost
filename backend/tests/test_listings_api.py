import os

from app.jobs import queue
from app.listings import store

VALID_URL = "https://www.rightmove.co.uk/properties/123456789"


def test_create_listing_creates_stub_and_enqueues_job(client):
    resp = client.post("/api/listings", json={"url": VALID_URL})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 123456789
    assert body["extraction_status"] in ("queued", "running", "done")

    jobs = queue.get_jobs_for_listing(123456789)
    assert any(j["job_type"] == "rightmove_extract" for j in jobs)


def test_create_listing_rejects_invalid_url(client):
    resp = client.post("/api/listings", json={"url": "https://www.zoopla.co.uk/property/1"})
    assert resp.status_code == 422


def test_create_listing_is_idempotent_for_same_url(client):
    client.post("/api/listings", json={"url": VALID_URL})
    client.post("/api/listings", json={"url": VALID_URL})

    jobs = [j for j in queue.get_jobs_for_listing(123456789) if j["job_type"] == "rightmove_extract"]
    assert len(jobs) == 1


def test_get_listing_404_for_unknown_id(client):
    assert client.get("/api/listings/999").status_code == 404


def test_get_listing_returns_serialized_listing(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1
    assert resp.json()["edited_fields"] == {}


def test_list_listings_filters_by_user_status(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    store.set_user_status(1, "active")
    store.set_user_status(2, "in_review")

    resp = client.get("/api/listings", params={"user_status": "active"})
    ids = [l["id"] for l in resp.json()]
    assert ids == [1]


def test_patch_listing_rejects_invalid_user_status(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "bogus"})
    assert resp.status_code == 422


def test_patch_listing_rejects_non_editable_field(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"fields": {"extraction_status": "done"}})
    assert resp.status_code == 422


def test_patch_listing_applies_manual_edit_and_marks_sticky(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"fields": {"price_gbp": 600000}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["price_gbp"] == 600000
    assert "price_gbp" in body["edited_fields"]


def test_patch_listing_toggles_user_status(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "active"})
    assert resp.json()["user_status"] == "active"


def test_delete_listing_removes_row_and_media(client, media_dir):
    store.create_stub_listing(1, VALID_URL)
    listing_media_dir = os.path.join(media_dir, "1")
    os.makedirs(listing_media_dir)

    resp = client.delete("/api/listings/1")
    assert resp.status_code == 204
    assert store.get_listing(1) is None
    assert not os.path.isdir(listing_media_dir)


def test_delete_listing_404_for_unknown_id(client):
    assert client.delete("/api/listings/999").status_code == 404


def test_refresh_listing_does_not_double_enqueue_while_pending(client):
    store.create_stub_listing(1, VALID_URL)
    queue.enqueue_job(1, "rightmove_extract", "http")

    client.post("/api/listings/1/refresh")

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "rightmove_extract"]
    assert len(jobs) == 1


def test_refresh_listing_enqueues_when_nothing_pending(client):
    store.create_stub_listing(1, VALID_URL)
    store.set_extraction_status(1, "done")

    resp = client.post("/api/listings/1/refresh")
    assert resp.status_code == 202

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "rightmove_extract"]
    assert len(jobs) == 1


def test_refresh_listing_404_for_unknown_id(client):
    assert client.post("/api/listings/999/refresh").status_code == 404


def test_get_jobs_for_listing(client):
    store.create_stub_listing(1, VALID_URL)
    queue.enqueue_job(1, "rightmove_extract", "http")

    resp = client.get("/api/listings/1/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_jobs_404_for_unknown_listing(client):
    assert client.get("/api/listings/999/jobs").status_code == 404
