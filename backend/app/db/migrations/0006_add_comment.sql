-- General-purpose comment field, independent of user_status/rejection_reason.
-- Unlike rejection_reason, it's never required and can be added/updated at
-- any time regardless of the listing's current status. No CHECK constraint
-- involved, so a straight ALTER TABLE is enough -- no table-rebuild dance
-- like 0002/0004.

ALTER TABLE listings ADD COLUMN comment TEXT;
