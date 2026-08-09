-- Admin-configured "standards" thresholds (e.g. floor_area_sqft lt 700,
-- cash_only eq true), evaluated against a listing on the detail page to
-- flag properties that don't meet the user's own baseline criteria. Purely
-- advisory -- evaluation never writes back to `listings`.

CREATE TABLE standards_rules (
    id         INTEGER PRIMARY KEY,
    field      TEXT NOT NULL,
    operator   TEXT NOT NULL CHECK (operator IN ('lt', 'lte', 'gt', 'gte', 'eq', 'neq')),
    value      TEXT NOT NULL,  -- stored as text, cast per field's type at eval time
    enabled    INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL
);
