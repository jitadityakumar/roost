-- Issue #59: raw candidate journey pool behind each destination_journeys
-- row, for an on-demand "why this journey was picked" details page.
-- listing_id is NOT NULL -- home journeys are explicitly out of scope, so
-- there is no home-origin variant the way home_journeys exists alongside
-- destination_journeys. Overwritten per scan (UNIQUE below), not an
-- append-only history -- same precedent as destination_journeys' own
-- delete-then-reinsert.
CREATE TABLE journey_scan_pools (
    id              INTEGER PRIMARY KEY,
    listing_id      INTEGER NOT NULL REFERENCES listings(id),
    destination_id  INTEGER NOT NULL REFERENCES frequent_destinations(id),
    scanned_at      TEXT NOT NULL,
    query_params    TEXT NOT NULL,
    candidate_pool  TEXT NOT NULL,
    UNIQUE(listing_id, destination_id)
);
