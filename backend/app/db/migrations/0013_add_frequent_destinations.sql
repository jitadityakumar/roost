-- Admin-defined places the user travels to often (office, family, an
-- airport terminal) with a target day-of-week + time and the CRS code of
-- their nearest national rail station -- see GitHub issue #28. day_of_week
-- is Python's date.weekday() convention (0 = Monday .. 6 = Sunday) so
-- app/destinations/compute.py can compare directly against date.today().

CREATE TABLE frequent_destinations (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    crs          TEXT NOT NULL,
    station_name TEXT NOT NULL,
    day_of_week  INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    time         TEXT NOT NULL,  -- "HH:MM", 24h, Europe/London wall-clock
    enabled      INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at   TEXT NOT NULL
);
