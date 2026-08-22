import json
import os

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point every DB connection at a fresh per-test SQLite file and apply
    migrations against it, so tests never touch the real data directory."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("ROOST_DB_PATH", db_path)

    from app.db.migrate import run_migrations
    from app.destinations import backfill_queue, backfill_status

    run_migrations()
    # backfill_status is deliberately process-wide, in-memory state (issue
    # #36) -- reset it per test too, same as the DB, so a leftover 'running'
    # entry from one test's destination_id can never be mistaken for a
    # fresh run's state in a later test that happens to reuse the same id.
    backfill_status._runs.clear()
    yield db_path

    # A destination backfill (issue #36, serialized via backfill_queue as
    # a follow-up) runs on a single process-wide worker thread that
    # outlives any individual test. Wait for the queue to fully drain
    # before returning -- otherwise a slow/queued backfill from this test
    # could still be running once monkeypatch (which tears down after this
    # fixture) reverts ROOST_DB_PATH, and would then hit the next test's
    # fresh, not-yet-migrated SQLite file.
    backfill_queue.wait_until_idle(timeout=5)


@pytest.fixture
def sample_property_data():
    with open(os.path.join(FIXTURES_DIR, "sample_property_data.json")) as f:
        return json.load(f)


@pytest.fixture
def mock_rightmove_network(monkeypatch, sample_property_data):
    """Stub out every network call the job handlers make (Rightmove page
    fetch + broadband API + postcodes.io council lookup + media downloads)
    with fixture data, so tests never hit the real internet — mirrors
    mocking rightmove_extract at the handlers boundary rather than touching
    the vendored scraper itself."""
    from app.jobs import handlers

    downloaded = []

    def fake_fetch_html(url):
        return "<html>irrelevant, resolve_page_model is also stubbed</html>"

    def fake_resolve_page_model(html):
        return {
            "propertyData": sample_property_data,
            "analyticsInfo": {"analyticsProperty": {"added": "20260115"}},
        }

    def fake_fetch_broadband_summary(postcode):
        return {
            "fastestAverageSpeed": {
                "display": "900 Mbps",
                "speedCategory": "Ultrafast",
                "provider": {"name": "Testnet"},
            },
            "cheapestDeal": {
                "speed": [{"display": "100 Mbps"}],
                "provider": {"name": "Testnet"},
                "subscription": {"averageMonthlyCost": 25},
            },
            "numberOfAvailableDeals": 4,
        }

    def fake_download_media(prop, out_dir):
        downloaded.append((prop, out_dir))
        return {"photos": 0, "floorplans": 0, "epc": 0}

    def fake_lookup_postcode(postcode):
        return {"admin_district": "Sampleton", "codes": {"admin_district": "E00000001"}}

    monkeypatch.setattr(handlers, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(handlers, "resolve_page_model", fake_resolve_page_model)
    monkeypatch.setattr(handlers, "fetch_broadband_summary", fake_fetch_broadband_summary)
    monkeypatch.setattr(handlers, "download_media", fake_download_media)
    monkeypatch.setattr(handlers, "lookup_postcode", fake_lookup_postcode)

    return downloaded


@pytest.fixture
def client(isolated_db, mock_rightmove_network, monkeypatch):
    from app import main

    # main.worker_pool/llm_worker_pool are process-wide singletons whose
    # internal asyncio state binds to the first event loop they ever run on.
    # Each TestClient spins up its own event loop, so letting the real pools
    # start here would break (and log noisy errors) on the second and later
    # tests that use this fixture. Route/handler tests below assert on
    # job-queue side effects and call handlers directly rather than relying
    # on a background pool actually draining jobs, so it's safe to no-op
    # both.
    monkeypatch.setattr(main.worker_pool, "start", lambda: None)
    monkeypatch.setattr(main.llm_worker_pool, "start", lambda: None)

    async def noop_stop():
        return None

    monkeypatch.setattr(main.worker_pool, "stop", noop_stop)
    monkeypatch.setattr(main.llm_worker_pool, "stop", noop_stop)

    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    """Redirect media storage to a temp dir for the duration of a test.
    MEDIA_DIR is bound at import time into each module that resolves a path
    from it at test time (`from app.config import MEDIA_DIR`), so each such
    bound name needs patching, not just app.config.MEDIA_DIR itself.
    handlers.MEDIA_DIR is deliberately NOT patched here: handlers.py only
    ever passes it straight through to download_media(), which
    mock_rightmove_network stubs out entirely — so its value never affects
    what a test actually reads or writes."""
    from app.jobs import llm_enqueue
    from app.routes import listings as listings_routes
    from app.routes import media as media_routes

    d = tmp_path / "media"
    d.mkdir()
    monkeypatch.setattr(listings_routes, "MEDIA_DIR", str(d))
    monkeypatch.setattr(media_routes, "MEDIA_DIR", str(d))
    monkeypatch.setattr(llm_enqueue, "MEDIA_DIR", str(d))
    return str(d)


@pytest.fixture
def mock_claude_cli(monkeypatch):
    """Stub handlers.run_claude_prompt so tests never shell out to the real
    `claude` CLI. `responses` is a list the test pushes raw stdout strings
    onto before calling a handler, consumed in call order (each handler
    makes exactly one call) — avoids matching on prompt text, since prompt
    wording is expected to change (see llm_prompts.py). Handlers now always
    pass `json_schema` and run the result through
    llm_client.parse_structured_output, so queued responses must be a
    `--output-format json` envelope (see test_llm_handlers.py's
    `_queue_response` helper), not a bare JSON object. `calls` records every
    invocation's args for assertions."""
    from app.jobs import handlers

    calls = []
    responses = []

    def fake_run_claude_prompt(
        prompt, model, timeout_s, allow_read=False, json_schema=None, disallow_all_tools=False
    ):
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "timeout_s": timeout_s,
                "allow_read": allow_read,
                "json_schema": json_schema,
                "disallow_all_tools": disallow_all_tools,
            }
        )
        if not responses:
            raise AssertionError("no mocked response queued for this claude -p call")
        return responses.pop(0)

    monkeypatch.setattr(handlers, "run_claude_prompt", fake_run_claude_prompt)
    return {"calls": calls, "responses": responses}
