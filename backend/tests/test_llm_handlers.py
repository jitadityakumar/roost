import json
import os

import pytest

from app.jobs import handlers, llm_prompts, queue
from app.listings import store


@pytest.fixture
def listing_id(client):  # client pulls in isolated_db + mock_rightmove_network
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def _job(listing_id, job_id=1):
    return {"id": job_id, "listing_id": listing_id}


def _queue_response(mock_claude_cli, payload: dict):
    # Matches the real `claude -p --output-format json` envelope shape (see
    # llm_client.parse_structured_output) — handlers now always pass
    # json_schema, so responses must be an envelope, not a bare object.
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(payload),
        "structured_output": payload,
        "total_cost_usd": 0.001,
        "duration_ms": 500,
    }
    mock_claude_cli["responses"].append(json.dumps(envelope))


# --- text_extract ---


def test_handle_text_extract_writes_all_fields(listing_id, mock_claude_cli):
    store.apply_extracted_fields(listing_id, {"description": "A lovely flat."})
    _queue_response(
        mock_claude_cli,
        {
            "lease_years_remaining": 90,
            "service_charge_pa": 1200,
            "council_tax_band": "D",
            "chain_free": True,
            "cash_only": False,
        },
    )

    handlers.handle_text_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["lease_years_remaining"] == 90
    assert listing["lease_years_remaining_source"] == "llm"
    assert listing["service_charge_pa"] == 1200
    assert listing["service_charge_pm"] == 100
    assert listing["service_charge_source"] == "llm"
    assert listing["council_tax_band"] == "D"
    assert listing["council_tax_band_source"] == "llm"
    assert listing["chain_free"] == 1
    assert listing["chain_free_source"] == "llm"
    assert listing["cash_only"] == 0
    assert listing["cash_only_source"] == "llm"
    assert mock_claude_cli["calls"][0]["allow_read"] is False
    assert mock_claude_cli["calls"][0]["disallow_all_tools"] is True
    assert mock_claude_cli["calls"][0]["json_schema"] == llm_prompts.TEXT_EXTRACT_SCHEMA


def test_handle_text_extract_only_writes_non_null_fields(listing_id, mock_claude_cli):
    store.apply_extracted_fields(listing_id, {"description": "A lovely flat."})
    _queue_response(
        mock_claude_cli,
        {
            "lease_years_remaining": None,
            "service_charge_pa": None,
            "council_tax_band": None,
            "chain_free": None,
            "cash_only": None,
        },
    )

    handlers.handle_text_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["lease_years_remaining"] is None
    assert listing["lease_years_remaining_source"] is None


def test_handle_text_extract_is_noop_when_no_description(listing_id, mock_claude_cli):
    handlers.handle_text_extract(_job(listing_id))
    assert mock_claude_cli["calls"] == []


def test_handle_text_extract_does_not_clobber_rightmove_sourced_fields(listing_id, mock_claude_cli):
    # council_tax_band came from Rightmove's structured data (PR #5); the LLM
    # read of the free-text description must not overwrite it.
    store.apply_extracted_fields(
        listing_id,
        {
            "description": "A lovely flat.",
            "council_tax_band": "D",
            "council_tax_band_source": "rightmove",
            "service_charge_pa": 1200,
            "service_charge_pm": 100,
            "service_charge_source": "rightmove",
        },
    )
    _queue_response(
        mock_claude_cli,
        {
            "lease_years_remaining": None,
            "service_charge_pa": 999,
            "council_tax_band": "F",
            "chain_free": None,
            "cash_only": None,
        },
    )

    handlers.handle_text_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["council_tax_band"] == "D"
    assert listing["council_tax_band_source"] == "rightmove"
    assert listing["service_charge_pa"] == 1200
    assert listing["service_charge_source"] == "rightmove"


def test_handle_text_extract_ignores_truthy_but_wrong_bool_strings(listing_id, mock_claude_cli):
    store.apply_extracted_fields(listing_id, {"description": "A lovely flat, no onward chain."})
    _queue_response(
        mock_claude_cli,
        {
            "lease_years_remaining": None,
            "service_charge_pa": None,
            "council_tax_band": None,
            "chain_free": "no",
            "cash_only": None,
        },
    )

    handlers.handle_text_extract(_job(listing_id))

    # "no" must not coerce to Python bool("no") == True and get stored as chain_free=1.
    assert store.get_listing(listing_id)["chain_free"] is None


def test_handle_text_extract_raises_on_unparseable_response(listing_id, mock_claude_cli):
    store.apply_extracted_fields(listing_id, {"description": "A lovely flat."})
    mock_claude_cli["responses"].append("Sorry, I can't help with that.")

    with pytest.raises(Exception):
        handlers.handle_text_extract(_job(listing_id))


# --- floor_area_vision ---


def test_handle_floor_area_vision_uses_sqft_directly(listing_id, media_dir, mock_claude_cli):
    d = os.path.join(media_dir, str(listing_id), "floorplans")
    os.makedirs(d)
    open(os.path.join(d, "01.jpeg"), "w").close()
    _queue_response(mock_claude_cli, {"floor_area_sqm": None, "floor_area_sqft": 850})

    handlers.handle_floor_area_vision(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["floor_area_sqft"] == 850
    assert listing["floor_area_sqft_source"] == "llm"
    assert mock_claude_cli["calls"][0]["allow_read"] is True
    assert mock_claude_cli["calls"][0]["json_schema"] == llm_prompts.FLOOR_AREA_VISION_SCHEMA


def test_handle_floor_area_vision_converts_sqm_to_sqft(listing_id, media_dir, mock_claude_cli):
    d = os.path.join(media_dir, str(listing_id), "floorplans")
    os.makedirs(d)
    open(os.path.join(d, "01.jpeg"), "w").close()
    _queue_response(mock_claude_cli, {"floor_area_sqm": 85, "floor_area_sqft": None})

    handlers.handle_floor_area_vision(_job(listing_id))

    from app.listings.normalize import sqm_to_sqft

    assert store.get_listing(listing_id)["floor_area_sqft"] == sqm_to_sqft(85)


def test_handle_floor_area_vision_raises_without_image(listing_id, media_dir):
    with pytest.raises(RuntimeError):
        handlers.handle_floor_area_vision(_job(listing_id))


# --- epc_vision ---


def test_handle_epc_vision_writes_both_fields(listing_id, media_dir, mock_claude_cli):
    d = os.path.join(media_dir, str(listing_id), "epc")
    os.makedirs(d)
    open(os.path.join(d, "01.jpeg"), "w").close()
    _queue_response(mock_claude_cli, {"epc_current": "C (73)", "epc_potential": "B (80)"})

    handlers.handle_epc_vision(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["epc_current"] == "C (73)"
    assert listing["epc_potential"] == "B (80)"
    assert listing["epc_source"] == "llm"
    assert mock_claude_cli["calls"][0]["json_schema"] == llm_prompts.EPC_VISION_SCHEMA


def test_handle_epc_vision_raises_without_image(listing_id, media_dir):
    with pytest.raises(RuntimeError):
        handlers.handle_epc_vision(_job(listing_id))


def test_handle_epc_vision_does_not_call_llm_when_rightmove_sourced(listing_id, media_dir, mock_claude_cli):
    d = os.path.join(media_dir, str(listing_id), "epc")
    os.makedirs(d)
    open(os.path.join(d, "01.jpeg"), "w").close()
    store.apply_extracted_fields(listing_id, {"epc_current": "A (95)", "epc_source": "rightmove"})

    handlers.handle_epc_vision(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["epc_current"] == "A (95)"
    assert listing["epc_source"] == "rightmove"
    assert mock_claude_cli["calls"] == []  # skipped before spending a serial-lane turn


def test_handle_text_extract_does_not_clobber_rightmove_sourced_lease_years(listing_id, mock_claude_cli):
    store.apply_extracted_fields(
        listing_id,
        {"description": "A lovely flat.", "lease_years_remaining": 999, "lease_years_remaining_source": "rightmove"},
    )
    _queue_response(
        mock_claude_cli,
        {
            "lease_years_remaining": 1,
            "service_charge_pa": None,
            "council_tax_band": None,
            "chain_free": None,
            "cash_only": None,
        },
    )

    handlers.handle_text_extract(_job(listing_id))

    listing = store.get_listing(listing_id)
    assert listing["lease_years_remaining"] == 999
    assert listing["lease_years_remaining_source"] == "rightmove"


# --- failure requeues via the existing job machinery ---


def test_llm_job_failure_requeues_via_fail_job(listing_id, media_dir, mock_claude_cli):
    d = os.path.join(media_dir, str(listing_id), "epc")
    os.makedirs(d)
    open(os.path.join(d, "01.jpeg"), "w").close()
    mock_claude_cli["responses"].append("not json at all")

    job_id = queue.enqueue_job(listing_id, "epc_vision", "llm")
    job = queue.claim_next_job("llm")
    assert job["id"] == job_id

    with pytest.raises(Exception):
        handlers.handle_epc_vision(job)
    queue.fail_job(job_id, "no parseable JSON")

    jobs = queue.get_jobs_for_listing(listing_id)
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["attempts"] == 1
