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
    assert body["already_tracked"] is False

    jobs = queue.get_jobs_for_listing(123456789)
    assert any(j["job_type"] == "rightmove_extract" for j in jobs)


def test_create_listing_flags_already_tracked_on_resubmit(client):
    client.post("/api/listings", json={"url": VALID_URL})
    resp = client.post("/api/listings", json={"url": VALID_URL})

    assert resp.status_code == 201
    assert resp.json()["already_tracked"] is True


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
    store.set_user_status(1, "approved")
    store.set_user_status(2, "triage")

    resp = client.get("/api/listings", params={"user_status": "approved"})
    ids = [l["id"] for l in resp.json()]
    assert ids == [1]


def test_list_listings_flags_has_warning_for_violating_listing(client):
    from app.standards import store as standards_store

    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.create_stub_listing(2, "https://www.rightmove.co.uk/properties/2")
    store.apply_extracted_fields(1, {"price_gbp": 600000})
    store.apply_extracted_fields(2, {"price_gbp": 400000})
    standards_store.create_rule("price_gbp", "gt", "500000")

    resp = client.get("/api/listings")
    flags = {l["id"]: l["has_warning"] for l in resp.json()}
    assert flags == {1: True, 2: False}


def test_patch_listing_rejects_invalid_user_status(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "bogus"})
    assert resp.status_code == 422


def test_patch_listing_rejects_without_reason(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "rejected"})
    assert resp.status_code == 422


def test_patch_listing_rejects_with_blank_reason(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "rejected", "rejection_reason": "   "})
    assert resp.status_code == 422


def test_patch_listing_rejects_with_reason_stores_it(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch(
        "/api/listings/1", json={"user_status": "rejected", "rejection_reason": "Too small"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_status"] == "rejected"
    assert body["rejection_reason"] == "Too small"


def test_patch_listing_approving_after_rejection_keeps_reason_as_history(client):
    store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"user_status": "rejected", "rejection_reason": "Too small"})
    resp = client.patch("/api/listings/1", json={"user_status": "approved"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_status"] == "approved"
    assert body["rejection_reason"] == "Too small"


def test_patch_listing_rejects_non_editable_field(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"fields": {"extraction_status": "done"}})
    assert resp.status_code == 422


def test_patch_listing_sets_comment(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"comment": "Nice garden"})
    assert resp.status_code == 200
    assert resp.json()["comment"] == "Nice garden"


def test_patch_listing_clears_comment_with_blank_string(client):
    store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"comment": "Nice garden"})
    resp = client.patch("/api/listings/1", json={"comment": ""})
    assert resp.status_code == 200
    assert resp.json()["comment"] is None


def test_patch_listing_clears_comment_with_whitespace_only(client):
    store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"comment": "Nice garden"})
    resp = client.patch("/api/listings/1", json={"comment": "   "})
    assert resp.status_code == 200
    assert resp.json()["comment"] is None


def test_patch_listing_comment_independent_of_status(client):
    store.create_stub_listing(1, VALID_URL)
    client.patch("/api/listings/1", json={"comment": "Nice garden"})
    resp = client.patch("/api/listings/1", json={"user_status": "approved"})
    assert resp.status_code == 200
    assert resp.json()["comment"] == "Nice garden"


def test_patch_listing_applies_manual_edit_and_marks_sticky(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"fields": {"price_gbp": 600000}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["price_gbp"] == 600000
    assert "price_gbp" in body["edited_fields"]


def test_get_listing_includes_council_tax_monthly_est(client):
    from app.counciltax import store as counciltax_store

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(
        1, {"admin_district": "Sampleton", "admin_district_gss": "E00000001", "council_tax_band": "D"}
    )
    counciltax_store.upsert_rates("E00000001", "Sampleton", {"band_d": 2340})

    resp = client.get("/api/listings/1")
    assert resp.json()["council_tax_monthly_est"] == 195
    assert resp.json()["admin_district"] == "Sampleton"


def test_get_listing_council_tax_monthly_est_null_without_rates(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.get("/api/listings/1")
    assert resp.json()["council_tax_monthly_est"] is None


def test_patch_council_tax_band_updates_estimate_without_reload(client):
    from app.counciltax import store as counciltax_store

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(1, {"admin_district": "Sampleton", "admin_district_gss": "E00000001"})
    counciltax_store.upsert_rates("E00000001", "Sampleton", {"band_d": 2340})

    resp = client.patch("/api/listings/1", json={"fields": {"council_tax_band": "D"}})
    assert resp.status_code == 200
    assert resp.json()["council_tax_monthly_est"] == 195


def test_patch_postcode_re_resolves_council(client, monkeypatch):
    from app.routes import listings as listings_route

    store.create_stub_listing(1, VALID_URL)
    monkeypatch.setattr(
        listings_route,
        "lookup_postcode",
        lambda postcode: {"admin_district": "New Council", "codes": {"admin_district": "E00000042"}},
    )

    resp = client.patch("/api/listings/1", json={"fields": {"postcode": "NW1 7JN"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["postcode"] == "NW1 7JN"
    assert body["admin_district"] == "New Council"
    assert body["admin_district_gss"] == "E00000042"


def test_patch_postcode_clears_council_when_unresolvable(client, monkeypatch):
    from app.routes import listings as listings_route

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(1, {"admin_district": "Old Council", "admin_district_gss": "E00000099"})
    monkeypatch.setattr(listings_route, "lookup_postcode", lambda postcode: None)

    resp = client.patch("/api/listings/1", json={"fields": {"postcode": "ZZ9 9ZZ"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["admin_district"] is None
    assert body["admin_district_gss"] is None


def test_patch_listing_toggles_user_status(client):
    store.create_stub_listing(1, VALID_URL)
    resp = client.patch("/api/listings/1", json={"user_status": "approved"})
    assert resp.json()["user_status"] == "approved"


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


def test_refresh_listing_skip_llm_persists_flag_on_job(client):
    store.create_stub_listing(1, VALID_URL)
    store.set_extraction_status(1, "done")

    resp = client.post("/api/listings/1/refresh?skip_llm=true")
    assert resp.status_code == 202

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "rightmove_extract"]
    assert len(jobs) == 1
    assert jobs[0]["skip_llm_chain"] == 1


def test_refresh_listing_without_skip_llm_defaults_to_false(client):
    store.create_stub_listing(1, VALID_URL)
    store.set_extraction_status(1, "done")

    client.post("/api/listings/1/refresh")

    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "rightmove_extract"]
    assert jobs[0]["skip_llm_chain"] == 0


def test_walk_refresh_404_for_unknown_id(client):
    assert client.post("/api/listings/999/walk-refresh").status_code == 404


def test_walk_refresh_recomputes_without_enqueueing_a_scrape_job(client, monkeypatch):
    import json

    from app.routes import listings as listings_route

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(
        1,
        {
            "latitude": 51.5,
            "longitude": -0.1,
            "nearest_stations_raw": json.dumps(
                [{"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]}]
            ),
        },
    )

    calls = []

    def fake_compute(listing_id, lat, lon, nearest):
        calls.append((listing_id, lat, lon, nearest))

    monkeypatch.setattr(listings_route, "compute_station_walk_distances", fake_compute)

    resp = client.post("/api/listings/1/walk-refresh")
    assert resp.status_code == 200
    assert calls == [(1, 51.5, -0.1, [{"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]}])]

    # No rightmove_extract job enqueued -- unlike /refresh, this never
    # touches the job queue at all.
    jobs = [j for j in queue.get_jobs_for_listing(1) if j["job_type"] == "rightmove_extract"]
    assert jobs == []


def test_walk_refresh_returns_fresh_walk_data_in_response(client, monkeypatch):
    import json

    from app.commute import walk_store
    from app.routes import listings as listings_route

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(
        1,
        {
            "latitude": 51.5,
            "longitude": -0.1,
            "nearest_stations_raw": json.dumps(
                [{"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]}]
            ),
        },
    )

    def fake_compute(listing_id, latitude, longitude, nearest_stations_raw):
        walk_store.replace_walk_distances(
            listing_id,
            [
                {
                    "station_index": 0,
                    "rightmove_name": "Clapham Junction Station",
                    "mode": "national-rail",
                    "stop_point_id": "910GCLPHMJC",
                    "distance_meters": 500,
                    "duration_seconds": 360,
                }
            ],
        )

    monkeypatch.setattr(listings_route, "compute_station_walk_distances", fake_compute)

    resp = client.post("/api/listings/1/walk-refresh")
    assert resp.status_code == 200
    nearest = resp.json()["nearest_stations_raw"]
    assert nearest[0]["walk_distance_meters"] == 500
    assert nearest[0]["walk_duration_seconds"] == 360


def test_get_listing_computes_min_walk_minutes_from_stored_walk_durations(client):
    import json

    from app.commute import walk_store
    from app.standards import store as standards_store

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(
        1,
        {
            "latitude": 51.5,
            "longitude": -0.1,
            "nearest_stations_raw": json.dumps(
                [
                    {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
                    {"name": "Vauxhall Station", "distance": 0.6, "types": ["NATIONAL_TRAIN"]},
                ]
            ),
        },
    )
    walk_store.replace_walk_distances(
        1,
        [
            {
                "station_index": 0,
                "rightmove_name": "Clapham Junction Station",
                "mode": "national-rail",
                "stop_point_id": "910GCLPHMJC",
                "distance_meters": 500,
                "duration_seconds": 900,
            },
            {
                "station_index": 1,
                "rightmove_name": "Vauxhall Station",
                "mode": "national-rail",
                "stop_point_id": "910GVAUXHLM",
                "distance_meters": 700,
                "duration_seconds": 660,
            },
        ],
    )
    # 660s -> 11 minutes is the minimum of the two stored durations -- confirms
    # the computed field takes the min across all stations, not just the first.
    standards_store.create_rule("min_walk_minutes", "gt", "10")

    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    violations = resp.json()["standards_violations"]
    assert any(v["field"] == "min_walk_minutes" for v in violations)
    matched = next(v for v in violations if v["field"] == "min_walk_minutes")
    assert "11" in matched["message"]


def test_get_listing_min_walk_minutes_ignores_stale_row_after_reorder(client):
    # station_walk_distances is index-keyed, not CRS-keyed -- if Rightmove
    # reorders nearest_stations_raw between the scrape that computed a walk
    # row and now, lookup_walk() discards any row whose stored rightmove_name
    # no longer matches the name currently at that index. min_walk_minutes
    # must read the already-guarded values _attach_walk_data attaches, not
    # the raw station_walk_distances table directly -- otherwise a stale row
    # from a station no longer among the listing's current nearest stations
    # could silently feed the computed min.
    import json

    from app.commute import walk_store
    from app.standards import store as standards_store

    store.create_stub_listing(1, VALID_URL)
    store.apply_extracted_fields(
        1,
        {
            "latitude": 51.5,
            "longitude": -0.1,
            # Reordered vs. the scrape that computed the walk rows below --
            # station_index 0 is now Vauxhall, not Clapham Junction.
            "nearest_stations_raw": json.dumps(
                [
                    {"name": "Vauxhall Station", "distance": 0.6, "types": ["NATIONAL_TRAIN"]},
                    {"name": "Clapham Junction Station", "distance": 0.4, "types": ["NATIONAL_TRAIN"]},
                ]
            ),
        },
    )
    walk_store.replace_walk_distances(
        1,
        [
            # Stored against the old ordering: index 0 -> Clapham Junction
            # (a fast 3 min walk), index 1 -> Vauxhall. Both are now stale --
            # neither rightmove_name matches the name at that index anymore.
            {
                "station_index": 0,
                "rightmove_name": "Clapham Junction Station",
                "mode": "national-rail",
                "stop_point_id": "910GCLPHMJC",
                "distance_meters": 200,
                "duration_seconds": 180,
            },
            {
                "station_index": 1,
                "rightmove_name": "Vauxhall Station",
                "mode": "national-rail",
                "stop_point_id": "910GVAUXHLM",
                "distance_meters": 700,
                "duration_seconds": 660,
            },
        ],
    )
    standards_store.create_rule("min_walk_minutes", "gt", "10")

    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    # Every stored row is stale (name mismatch at its index), so no walk data
    # should be usable at all -- must not silently pick up the stale 3 min
    # Clapham Junction row and wrongly report no violation.
    violations = resp.json()["standards_violations"]
    assert not any(v["field"] == "min_walk_minutes" for v in violations)


def test_get_listing_min_walk_minutes_null_when_no_walk_data(client):
    from app.standards import store as standards_store

    store.create_stub_listing(1, VALID_URL)
    standards_store.create_rule("min_walk_minutes", "gt", "10")

    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    violations = resp.json()["standards_violations"]
    assert not any(v["field"] == "min_walk_minutes" for v in violations)


def test_walk_refresh_handles_listing_with_no_stations_or_latlon(client):
    # No latitude/longitude/nearest_stations_raw at all -- must not 500,
    # same "just no data" degrade-gracefully path as the scrape-time call.
    store.create_stub_listing(1, VALID_URL)

    resp = client.post("/api/listings/1/walk-refresh")
    assert resp.status_code == 200


def test_walk_refresh_skips_recompute_while_rightmove_extract_pending(client, monkeypatch):
    # Guards against racing an in-flight scrape: that job's own
    # compute_station_walk_distances call is about to write fresh rows
    # keyed against the *new* nearest_stations_raw it's fetching -- this
    # route must not race ahead and overwrite them with stale ones, same
    # has_pending_job guard /refresh uses.
    from app.routes import listings as listings_route

    store.create_stub_listing(1, VALID_URL)
    queue.enqueue_job(1, "rightmove_extract", "http")

    def boom(*a):
        raise AssertionError("compute_station_walk_distances should not run while a scrape is pending")

    monkeypatch.setattr(listings_route, "compute_station_walk_distances", boom)

    resp = client.post("/api/listings/1/walk-refresh")
    assert resp.status_code == 200


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
