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
    assert body["pipeline_status"] == "queued"

    jobs = queue.get_jobs_for_listing(123456789)
    assert any(j["job_type"] == "rightmove_extract" for j in jobs)


def test_pipeline_status_is_none_for_listing_with_no_jobs(client):
    # create_stub_listing bypasses the route (and its job enqueue) --
    # exercises the "no jobs table rows at all" branch.
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    resp = client.get("/api/listings/1")
    assert resp.json()["pipeline_status"] is None


def test_pipeline_status_is_fetching_while_media_download_in_flight(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    rm_job_id = queue.enqueue_job(1, "rightmove_extract", "http")
    queue.complete_job(rm_job_id)
    queue.enqueue_job(1, "media_download", "http")

    resp = client.get("/api/listings/1")
    assert resp.json()["pipeline_status"] == "fetching"


def test_pipeline_status_is_failed_when_a_job_permanently_fails(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    rm_job_id = queue.enqueue_job(1, "rightmove_extract", "http")
    queue.fail_job(rm_job_id, "boom", permanent=True)

    resp = client.get("/api/listings/1")
    assert resp.json()["pipeline_status"] == "failed"


def test_list_listings_includes_pipeline_status_without_n_plus_1(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    queue.enqueue_job(1, "rightmove_extract", "http")
    queue.enqueue_job(2, "rightmove_extract", "http")

    resp = client.get("/api/listings")
    statuses = {l["id"]: l["pipeline_status"] for l in resp.json()}
    assert statuses == {1: "queued", 2: "queued"}


def test_list_listings_attributes_distinct_pipeline_status_per_listing(client):
    # Three listings simultaneously in three different pipeline stages --
    # exercises that the aggregate query in queue.latest_job_statuses_for_listings
    # correctly scopes rows per listing_id rather than mixing them up.
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    store.create_stub_listing(3, "https://www.rightmove.co.uk/properties/3")

    queue.enqueue_job(1, "rightmove_extract", "http")  # stays queued

    rm2 = queue.enqueue_job(2, "rightmove_extract", "http")
    queue.complete_job(rm2)
    md2 = queue.enqueue_job(2, "media_download", "http")
    queue.complete_job(md2)
    queue.enqueue_job(2, "text_extract", "llm")  # queued -> processing

    rm3 = queue.enqueue_job(3, "rightmove_extract", "http")
    queue.complete_job(rm3)
    md3 = queue.enqueue_job(3, "media_download", "http")
    queue.complete_job(md3)  # nothing else in flight -> done

    resp = client.get("/api/listings")
    statuses = {l["id"]: l["pipeline_status"] for l in resp.json()}
    assert statuses == {1: "queued", 2: "processing", 3: None}


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


def test_llm_refresh_404_for_unknown_id(client):
    assert client.post("/api/listings/999/llm-refresh").status_code == 404


def test_llm_refresh_enqueues_text_extract_when_description_present(client):
    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(1, {"description": "A lovely flat."})

    resp = client.post("/api/listings/1/llm-refresh")
    assert resp.status_code == 202
    assert resp.json()["enqueued"] == ["text_extract"]

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "text_extract"]
    assert len(jobs) == 1


def test_llm_refresh_skips_vision_jobs_without_images_on_disk(client, media_dir):
    store.create_stub_listing(1, VALID_URL)

    resp = client.post("/api/listings/1/llm-refresh")
    assert resp.status_code == 202
    assert "floor_area_vision" not in resp.json()["enqueued"]
    assert "epc_vision" not in resp.json()["enqueued"]


def test_llm_refresh_enqueues_vision_jobs_when_images_present(client, media_dir):
    store.create_stub_listing(1, VALID_URL)
    for category in ("floorplans", "epc"):
        d = os.path.join(media_dir, "1", category)
        os.makedirs(d)
        open(os.path.join(d, "01.jpeg"), "w").close()

    resp = client.post("/api/listings/1/llm-refresh")
    assert resp.status_code == 202
    assert set(resp.json()["enqueued"]) >= {"floor_area_vision", "epc_vision"}


def test_llm_refresh_does_not_double_enqueue_while_pending(client):
    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(1, {"description": "A lovely flat."})
    queue.enqueue_job(1, "text_extract", "llm")

    resp = client.post("/api/listings/1/llm-refresh")
    assert resp.json()["enqueued"] == []

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "text_extract"]
    assert len(jobs) == 1


def test_llm_refresh_skips_hand_edited_fields(client):
    # A field the user has manually corrected must not be silently
    # overwritten by a backfill re-run — same stickiness rule /refresh
    # already respects.
    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(1, {"description": "A lovely flat."})
    store.apply_manual_edit(
        1,
        {
            "lease_years_remaining": 999,
            "service_charge_pa": 1,
            "service_charge_pm": 1,
            "council_tax_band": "A",
            "chain_free": True,
            "cash_only": False,
        },
    )

    resp = client.post("/api/listings/1/llm-refresh")
    assert resp.json()["enqueued"] == []


def test_get_jobs_for_listing(client):
    store.create_stub_listing(1, VALID_URL)
    queue.enqueue_job(1, "rightmove_extract", "http")

    resp = client.get("/api/listings/1/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_jobs_404_for_unknown_listing(client):
    assert client.get("/api/listings/999/jobs").status_code == 404
