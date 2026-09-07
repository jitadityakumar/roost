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

// Home page's nav order/wording is its own concern, deliberately separate
// from USER_STATUSES (which drives route generation and the status-change
// menu, where a different order is more natural) -- user-requested layout.
export const HOME_MENU_ORDER = ["viewing", "contacted", "approved", "triage", "rejected"];

// Statuses whose entry requires a mandatory comment (+ initials) -- mirrors
// backend/app/routes/listings.py's STATUS_REQUIRED_FIELDS. The verb fills
// in the comment box's label, e.g. "Reason for rejecting".
export const STATUS_COMMENT_VERB = {
  rejected: "reason for rejecting",
  viewing: "note for the viewing",
  contacted: "note on contacting the agent",
};

// Same color mapping as .status-dot/.home-option/.status-menu in
// index.css, exposed for places (the shortlist map, issue #86) that need
// an actual color value rather than a CSS class -- e.g. Leaflet's SVG
// marker renderer sets color as a presentation attribute, which can't
// reference a `var(...)` the way a stylesheet rule can. Read via
// getComputedStyle so the map still follows dark-mode overrides; the
// fallback is only exercised where index.css isn't loaded (tests).
export const STATUS_COLOR_VAR = {
  triage: { cssVar: "--muted", fallback: "#666" },
  approved: { cssVar: "--accent", fallback: "#2a6f4f" },
  rejected: { cssVar: "--danger", fallback: "#b3261e" },
  viewing: { cssVar: "--edit-color", fallback: "#2563eb" },
  contacted: { cssVar: "--warn", fallback: "#b8860b" },
};
