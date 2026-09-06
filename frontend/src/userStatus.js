// Shared between App/Home (routes/nav), ListingsPage, ListingCard, and
// ListingDetail (status-change menu) so the 5 statuses can't drift out of
// sync -- adding a status here is enough to get a new tab/route and menu
// entry, no per-status branching elsewhere (issue #82).
export const USER_STATUS_LABEL = {
  triage: "Triage",
  approved: "Approved",
  rejected: "Rejected",
  viewing: "Viewing",
  contacted: "Contacted",
};

export const USER_STATUSES = Object.keys(USER_STATUS_LABEL);

// Statuses whose entry requires a mandatory comment (+ initials) -- mirrors
// backend/app/routes/listings.py's STATUS_REQUIRED_FIELDS. The verb fills
// in the comment box's label, e.g. "Reason for rejecting".
export const STATUS_COMMENT_VERB = {
  rejected: "reason for rejecting",
  viewing: "note for the viewing",
  contacted: "note on contacting the agent",
};
