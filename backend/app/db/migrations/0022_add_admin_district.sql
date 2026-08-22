-- Issue #60: resolved council (name + GSS code) per listing, via
-- postcodes.io, mirroring the crime feature's existing client. Two separate
-- migrations (this ALTER, and 0023's CREATE) rather than one file --
-- SQLite has no ADD COLUMN IF NOT EXISTS, so a crash between this ALTER and
-- the CREATE would otherwise replay the whole file on next boot and die on
-- "duplicate column name."
ALTER TABLE listings ADD COLUMN admin_district TEXT;
ALTER TABLE listings ADD COLUMN admin_district_gss TEXT;
