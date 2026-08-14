import pytest

from app.jobs import handlers, queue
from app.listings import store


@pytest.fixture
def listing_id(client):  # client pulls in isolated_db + mock_rightmove_network
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def _job(listing_id, job_id=1, skip_llm_chain=False, skip_maps=False):
    return {
        "id": job_id,
        "listing_id": listing_id,
        "skip_llm_chain": int(skip_llm_chain),
        "skip_maps": int(skip_maps),
    }


def test_handle_rightmove_extract_maps_fields(listing_id):
    handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["price_gbp"] == 475000
    assert listing["address"] == "1 Test Street, Sampleton"
    assert listing["postcode"] == "SM1 2AB"
    assert listing["tenure"] == "Freehold"
    assert listing["garden"] == 1
    assert listing["garden_source"] == "rightmove"
    assert listing["parking"] == "Garage"
    assert listing["council_tax_band"] == "D"
    assert listing["council_tax_band_source"] == "rightmove"
    assert listing["service_charge_pa"] == 1200
    assert listing["service_charge_pm"] == 100
    assert listing["broadband_top_speed"] == "900 Mbps"
    assert listing["broadband_top_speed_provider"] == "Testnet"
    assert listing["extraction_status"] == "done"
    assert listing["listing_added_on"] == "2026-01-15"
    assert listing["rightmove_fetched_at"] is not None
    assert listing["latitude"] == 51.5074
    assert listing["longitude"] == -0.1278
    assert listing["pin_type"] == "APPROXIMATE_POINT"


def test_handle_rightmove_extract_nulls_lease_years_for_freehold_zero(listing_id, sample_property_data, monkeypatch):
    sample_property_data["tenure"] = {"tenureType": "FREEHOLD", "yearsRemainingOnLease": 0}
    monkeypatch.setattr(handlers, "resolve_page_model", lambda html: {"propertyData": sample_property_data})

    handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["tenure"] == "FREEHOLD"
    assert listing["lease_years_remaining"] is None
    assert listing["lease_years_remaining_source"] is None


def test_handle_rightmove_extract_keeps_lease_years_for_non_freehold_zero(
    listing_id, sample_property_data, monkeypatch
):
    sample_property_data["tenure"] = {"tenureType": "LEASEHOLD", "yearsRemainingOnLease": 0}
    monkeypatch.setattr(handlers, "resolve_page_model", lambda html: {"propertyData": sample_property_data})

    handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["tenure"] == "LEASEHOLD"
    assert listing["lease_years_remaining"] == 0
    assert listing["lease_years_remaining_source"] == "rightmove"


def test_handle_rightmove_extract_handles_missing_added_on(listing_id, sample_property_data, monkeypatch):
    monkeypatch.setattr(handlers, "resolve_page_model", lambda html: {"propertyData": sample_property_data})

    handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["listing_added_on"] is None
    assert listing["rightmove_fetched_at"] is not None


def test_handle_rightmove_extract_chains_media_download(listing_id):
    # depends_on_job_id has a real FK to jobs(id), so the parent job must
    # actually be enqueued (not just a fabricated job id) for this to work.
    parent_job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")

    handlers.handle_rightmove_extract(_job(listing_id, job_id=parent_job_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    media_jobs = [j for j in jobs if j["job_type"] == "media_download"]
    assert len(media_jobs) == 1
    assert media_jobs[0]["depends_on_job_id"] == parent_job_id


def test_handle_rightmove_extract_swallows_broadband_failure(listing_id, monkeypatch):
    def boom(postcode):
        raise RuntimeError("broadband API down")

    monkeypatch.setattr(handlers, "fetch_broadband_summary", boom)

    handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["extraction_status"] == "done"
    assert listing["broadband_top_speed"] is None


def test_handle_rightmove_extract_marks_failed_on_fetch_error(listing_id, monkeypatch):
    def boom(url):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(handlers, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        handlers.handle_rightmove_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["extraction_status"] == "failed"
    assert listing["extraction_error"] == "network unreachable"


def test_handle_rightmove_extract_skips_blank_council_tax_band(listing_id, sample_property_data, monkeypatch):
    sample_property_data["livingCosts"]["councilTaxBand"] = "TBC"
    monkeypatch.setattr(handlers, "resolve_page_model", lambda html: {"propertyData": sample_property_data})

    handlers.handle_rightmove_extract(_job(listing_id))

    assert store.get_listing(listing_id)["council_tax_band"] is None


def test_handle_rightmove_extract_raises_for_unknown_listing():
    with pytest.raises(RuntimeError):
        handlers.handle_rightmove_extract(_job(listing_id=12345))


def test_handle_rightmove_extract_stores_walk_distances_for_resolved_stations(listing_id, monkeypatch):
    from app.commute import walk_store

    monkeypatch.setattr(
        handlers,
        "resolve_crs_codes",
        lambda raw: [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4}],
    )
    monkeypatch.setattr(handlers, "latlong_for_crs", lambda crs: (51.4695, -0.1706))
    monkeypatch.setattr(
        handlers, "compute_walk_distance", lambda *a: {"distance_meters": 500, "duration_seconds": 360}
    )

    handlers.handle_rightmove_extract(_job(listing_id))

    assert walk_store.get_walk_distances(listing_id) == {
        "CLJ": {"distance_meters": 500, "duration_seconds": 360}
    }


def test_handle_rightmove_extract_swallows_walking_api_failure(listing_id, monkeypatch):
    from app.commute import walk_store
    from app.commute.walking import WalkingApiError

    monkeypatch.setattr(
        handlers,
        "resolve_crs_codes",
        lambda raw: [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4}],
    )
    monkeypatch.setattr(handlers, "latlong_for_crs", lambda crs: (51.4695, -0.1706))

    def boom(*a):
        raise WalkingApiError("no key")

    monkeypatch.setattr(handlers, "compute_walk_distance", boom)

    handlers.handle_rightmove_extract(_job(listing_id))  # should not raise

    assert store.get_listing(listing_id)["extraction_status"] == "done"
    assert walk_store.get_walk_distances(listing_id) == {}


def test_handle_rightmove_extract_skips_walk_distances_without_listing_latlon(
    listing_id, sample_property_data, monkeypatch
):
    from app.commute import walk_store

    sample_property_data.pop("location", None)
    monkeypatch.setattr(handlers, "resolve_page_model", lambda html: {"propertyData": sample_property_data})

    handlers.handle_rightmove_extract(_job(listing_id))

    assert walk_store.get_walk_distances(listing_id) == {}


def test_handle_rightmove_extract_skip_maps_does_not_call_walking_api(listing_id, monkeypatch):
    from app.commute import walk_store

    monkeypatch.setattr(
        handlers,
        "resolve_crs_codes",
        lambda raw: [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4}],
    )
    monkeypatch.setattr(handlers, "latlong_for_crs", lambda crs: (51.4695, -0.1706))

    def boom(*a):
        raise AssertionError("compute_walk_distance should not be called when skip_maps is set")

    monkeypatch.setattr(handlers, "compute_walk_distance", boom)

    handlers.handle_rightmove_extract(_job(listing_id, skip_maps=True))

    assert store.get_listing(listing_id)["extraction_status"] == "done"
    assert walk_store.get_walk_distances(listing_id) == {}


def test_handle_rightmove_extract_skip_maps_leaves_existing_walk_distances_untouched(listing_id, monkeypatch):
    from app.commute import walk_store

    monkeypatch.setattr(
        handlers,
        "resolve_crs_codes",
        lambda raw: [{"name": "Clapham Junction", "crs": "CLJ", "distance": 0.4}],
    )
    monkeypatch.setattr(handlers, "latlong_for_crs", lambda crs: (51.4695, -0.1706))
    monkeypatch.setattr(
        handlers, "compute_walk_distance", lambda *a: {"distance_meters": 500, "duration_seconds": 360}
    )
    handlers.handle_rightmove_extract(_job(listing_id))
    assert walk_store.get_walk_distances(listing_id) == {
        "CLJ": {"distance_meters": 500, "duration_seconds": 360}
    }

    def boom(*a):
        raise AssertionError("compute_walk_distance should not be called when skip_maps is set")

    monkeypatch.setattr(handlers, "compute_walk_distance", boom)

    handlers.handle_rightmove_extract(_job(listing_id, skip_maps=True))

    assert walk_store.get_walk_distances(listing_id) == {
        "CLJ": {"distance_meters": 500, "duration_seconds": 360}
    }


def test_handle_media_download_uses_latest_snapshot(listing_id, media_dir):
    store.insert_snapshot(listing_id, 500000, None, {"id": "raw-id-from-rightmove"})

    handlers.handle_media_download(_job(listing_id))  # should not raise


def test_handle_media_download_raises_without_snapshot(listing_id, media_dir):
    with pytest.raises(RuntimeError):
        handlers.handle_media_download(_job(listing_id))


def test_handle_rightmove_extract_chains_text_extract(listing_id):
    parent_job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http")

    handlers.handle_rightmove_extract(_job(listing_id, job_id=parent_job_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    text_jobs = [j for j in jobs if j["job_type"] == "text_extract"]
    assert len(text_jobs) == 1
    assert text_jobs[0]["depends_on_job_id"] == parent_job_id


def test_handle_rightmove_extract_does_not_duplicate_pending_text_extract(listing_id):
    # A text_extract job already queued/running for this listing (e.g. from
    # a prior Refresh) must not get a second one enqueued behind it — the
    # llm lane is strictly serial, so a duplicate is a wasted turn, not just
    # redundant.
    queue.enqueue_job(listing_id, "text_extract", "llm")

    handlers.handle_rightmove_extract(_job(listing_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert len([j for j in jobs if j["job_type"] == "text_extract"]) == 1


def test_handle_rightmove_extract_skips_text_extract_when_all_target_fields_sticky(listing_id):
    store.apply_manual_edit(
        listing_id,
        {
            "lease_years_remaining": 90,
            "service_charge_pa": 500,
            "service_charge_pm": 42,
            "council_tax_band": "F",
            "chain_free": 1,
            "cash_only": 0,
        },
    )

    handlers.handle_rightmove_extract(_job(listing_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert not [j for j in jobs if j["job_type"] == "text_extract"]


def test_handle_rightmove_extract_still_enqueues_text_extract_when_only_some_fields_sticky(listing_id):
    store.apply_manual_edit(listing_id, {"chain_free": 1})

    handlers.handle_rightmove_extract(_job(listing_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert len(jobs) and [j for j in jobs if j["job_type"] == "text_extract"]


def test_handle_rightmove_extract_skip_llm_chain_still_enqueues_media_download(listing_id):
    parent_job_id = queue.enqueue_job(listing_id, "rightmove_extract", "http", skip_llm_chain=True)

    handlers.handle_rightmove_extract(_job(listing_id, job_id=parent_job_id, skip_llm_chain=True))

    jobs = queue.get_jobs_for_listing(listing_id)
    media_jobs = [j for j in jobs if j["job_type"] == "media_download"]
    assert len(media_jobs) == 1
    assert media_jobs[0]["skip_llm_chain"] == 1


def test_handle_rightmove_extract_skip_llm_chain_does_not_enqueue_text_extract(listing_id):
    handlers.handle_rightmove_extract(_job(listing_id, skip_llm_chain=True))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert not [j for j in jobs if j["job_type"] == "text_extract"]


def test_handle_media_download_chains_vision_jobs_when_media_present(listing_id, media_dir):
    import os

    store.insert_snapshot(listing_id, 500000, None, {"id": "raw-id-from-rightmove"})
    floorplans_dir = os.path.join(media_dir, str(listing_id), "floorplans")
    epc_dir = os.path.join(media_dir, str(listing_id), "epc")
    os.makedirs(floorplans_dir)
    os.makedirs(epc_dir)
    open(os.path.join(floorplans_dir, "01.jpeg"), "w").close()
    open(os.path.join(epc_dir, "01.jpeg"), "w").close()

    parent_job_id = queue.enqueue_job(listing_id, "media_download", "http")
    handlers.handle_media_download(_job(listing_id, job_id=parent_job_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    job_types = {j["job_type"] for j in jobs}
    assert "floor_area_vision" in job_types
    assert "epc_vision" in job_types
    for j in jobs:
        if j["job_type"] in ("floor_area_vision", "epc_vision"):
            assert j["depends_on_job_id"] == parent_job_id


def test_handle_media_download_skip_llm_chain_does_not_enqueue_vision_jobs(listing_id, media_dir):
    import os

    store.insert_snapshot(listing_id, 500000, None, {"id": "raw-id-from-rightmove"})
    floorplans_dir = os.path.join(media_dir, str(listing_id), "floorplans")
    epc_dir = os.path.join(media_dir, str(listing_id), "epc")
    os.makedirs(floorplans_dir)
    os.makedirs(epc_dir)
    open(os.path.join(floorplans_dir, "01.jpeg"), "w").close()
    open(os.path.join(epc_dir, "01.jpeg"), "w").close()

    handlers.handle_media_download(_job(listing_id, skip_llm_chain=True))

    jobs = queue.get_jobs_for_listing(listing_id)
    job_types = {j["job_type"] for j in jobs}
    assert "floor_area_vision" not in job_types
    assert "epc_vision" not in job_types


def test_handle_media_download_skips_vision_jobs_without_media(listing_id, media_dir):
    store.insert_snapshot(listing_id, 500000, None, {"id": "raw-id-from-rightmove"})

    handlers.handle_media_download(_job(listing_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    job_types = {j["job_type"] for j in jobs}
    assert "floor_area_vision" not in job_types
    assert "epc_vision" not in job_types


def test_handle_media_download_skips_vision_jobs_when_sticky(listing_id, media_dir):
    import os

    store.insert_snapshot(listing_id, 500000, None, {"id": "raw-id-from-rightmove"})
    floorplans_dir = os.path.join(media_dir, str(listing_id), "floorplans")
    os.makedirs(floorplans_dir)
    open(os.path.join(floorplans_dir, "01.jpeg"), "w").close()
    store.apply_manual_edit(listing_id, {"floor_area_sqft": 850})

    handlers.handle_media_download(_job(listing_id))

    jobs = queue.get_jobs_for_listing(listing_id)
    assert not [j for j in jobs if j["job_type"] == "floor_area_vision"]
