-- Issue #61: postcodes.io-derived local-politics fields per listing. Derived
-- and non-sticky, exactly like admin_district/admin_district_gss (0022) --
-- always overwritten from the listing's current postcode, never hand-edited.
ALTER TABLE listings ADD COLUMN admin_ward TEXT;
ALTER TABLE listings ADD COLUMN admin_ward_gss TEXT;
ALTER TABLE listings ADD COLUMN parish TEXT;
ALTER TABLE listings ADD COLUMN admin_county TEXT;
ALTER TABLE listings ADD COLUMN constituency TEXT;
ALTER TABLE listings ADD COLUMN constituency_gss TEXT;
