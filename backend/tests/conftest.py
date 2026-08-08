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

    run_migrations()
    yield db_path


@pytest.fixture
def sample_property_data():
    with open(os.path.join(FIXTURES_DIR, "sample_property_data.json")) as f:
        return json.load(f)


@pytest.fixture
def mock_rightmove_network(monkeypatch, sample_property_data):
    """Stub out every network call the job handlers make (Rightmove page
    fetch + broadband API + media downloads) with fixture data, so tests
    never hit the real internet — mirrors mocking rightmove_extract at the
    handlers boundary rather than touching the vendored scraper itself."""
    from app.jobs import handlers

    downloaded = []

    def fake_fetch_html(url):
        return "<html>irrelevant, resolve_page_model is also stubbed</html>"

    def fake_resolve_page_model(html):
        return {"propertyData": sample_property_data}

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

    monkeypatch.setattr(handlers, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(handlers, "resolve_page_model", fake_resolve_page_model)
    monkeypatch.setattr(handlers, "fetch_broadband_summary", fake_fetch_broadband_summary)
    monkeypatch.setattr(handlers, "download_media", fake_download_media)

    return downloaded


@pytest.fixture
def client(isolated_db, mock_rightmove_network, monkeypatch):
    from app import main

    # main.worker_pool is a process-wide singleton whose internal
    # asyncio.Lock binds to the first event loop it ever runs on. Each
    # TestClient spins up its own event loop, so letting the real pool start
    # here would break (and log noisy errors) on the second and later tests
    # that use this fixture. Route/handler tests below assert on job-queue
    # side effects and call handlers directly rather than relying on the
    # background pool actually draining jobs, so it's safe to no-op it.
    monkeypatch.setattr(main.worker_pool, "start", lambda: None)

    async def noop_stop():
        return None

    monkeypatch.setattr(main.worker_pool, "stop", noop_stop)

    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    """Redirect media storage to a temp dir for the duration of a test.
    MEDIA_DIR is bound at import time into each route module (`from
    app.config import MEDIA_DIR`), so both bound names need patching, not
    just app.config.MEDIA_DIR itself."""
    from app.routes import listings as listings_routes
    from app.routes import media as media_routes

    d = tmp_path / "media"
    d.mkdir()
    monkeypatch.setattr(listings_routes, "MEDIA_DIR", str(d))
    monkeypatch.setattr(media_routes, "MEDIA_DIR", str(d))
    return str(d)
