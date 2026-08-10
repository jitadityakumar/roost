-- Lets a rightmove_extract (and its dependent media_download) job opt out of
-- auto-chaining the llm-lane jobs (text_extract/floor_area_vision/
-- epc_vision). Needed for POST /refresh?skip_llm=true, used by
-- scripts/backfill-rightmove.sh --skip-llm to bulk re-scrape (e.g. after a
-- rightmove_extract.py field-mapping change) without triggering real,
-- billed claude -p calls for every listing.

ALTER TABLE jobs ADD COLUMN skip_llm_chain INTEGER NOT NULL DEFAULT 0;
