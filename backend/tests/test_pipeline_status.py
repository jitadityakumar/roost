from app.jobs.pipeline_status import derive_pipeline_status


def test_no_jobs_yet_returns_none():
    assert derive_pipeline_status({}) is None


def test_rightmove_extract_queued():
    assert derive_pipeline_status({"rightmove_extract": "queued"}) == "queued"


def test_rightmove_extract_running_is_fetching():
    assert derive_pipeline_status({"rightmove_extract": "running"}) == "fetching"


def test_rightmove_done_media_download_in_flight_is_fetching():
    assert derive_pipeline_status({"rightmove_extract": "done", "media_download": "running"}) == "fetching"


def test_http_lane_done_llm_lane_in_flight_is_processing():
    assert (
        derive_pipeline_status(
            {"rightmove_extract": "done", "media_download": "done", "text_extract": "queued"}
        )
        == "processing"
    )


def test_all_done_returns_none():
    assert (
        derive_pipeline_status(
            {
                "rightmove_extract": "done",
                "media_download": "done",
                "text_extract": "done",
                "floor_area_vision": "done",
                "epc_vision": "done",
            }
        )
        is None
    )


def test_job_type_never_enqueued_is_not_treated_as_pending():
    # e.g. no floorplan image on disk -> floor_area_vision was never
    # enqueued at all, not left "queued" forever.
    assert (
        derive_pipeline_status(
            {"rightmove_extract": "done", "media_download": "done", "text_extract": "done"}
        )
        is None
    )


def test_any_failed_job_wins_over_later_in_progress_stages():
    assert (
        derive_pipeline_status(
            {
                "rightmove_extract": "done",
                "media_download": "done",
                "text_extract": "failed",
                "floor_area_vision": "running",
            }
        )
        == "failed"
    )


def test_rightmove_extract_failed_before_anything_else_enqueued():
    assert derive_pipeline_status({"rightmove_extract": "failed"}) == "failed"


def test_stale_media_download_failure_does_not_mask_a_fresh_refresh():
    # A Refresh only re-enqueues rightmove_extract immediately -- media_download
    # doesn't get a fresh row until the new rightmove_extract job completes (see
    # handlers.py). A prior failed media_download row is stale here and must
    # not override the fresh rightmove_extract run that's actually in progress.
    assert (
        derive_pipeline_status({"rightmove_extract": "queued", "media_download": "failed"}) == "queued"
    )
    assert (
        derive_pipeline_status({"rightmove_extract": "running", "media_download": "failed"}) == "fetching"
    )


def test_stale_llm_lane_failure_does_not_mask_media_download_in_flight():
    assert (
        derive_pipeline_status(
            {"rightmove_extract": "done", "media_download": "running", "text_extract": "failed"}
        )
        == "fetching"
    )


def test_media_download_failure_reported_once_its_stage_is_reached():
    assert (
        derive_pipeline_status({"rightmove_extract": "done", "media_download": "failed"}) == "failed"
    )
