-- Issue #61: register the Local Politics section in the #93 detail-page
-- sections config. DEFAULT 0 so the existing singleton row starts collapsed.
ALTER TABLE detail_page_sections_config ADD COLUMN local_politics_expanded INTEGER NOT NULL DEFAULT 0;
