// Client-side filter/sort logic for the status list pages (issue #124).
// Options and counts are always derived from the *unfiltered* listings so
// choices don't disappear as other filters are applied.

export const TENURE_OPTIONS = [
  { value: "FREEHOLD", label: "Freehold" },
  { value: "LEASEHOLD", label: "Leasehold" },
  { value: "SHARE_OF_FREEHOLD", label: "Share of freehold" },
  { value: "UNKNOWN", label: "Unknown" },
];
export const EPC_BANDS = ["A", "B", "C", "D", "E", "F", "G"];

export const EMPTY_FILTERS = { tenure: [], epc: [], chainFree: false };

const KNOWN_TENURES = new Set(["FREEHOLD", "LEASEHOLD", "SHARE_OF_FREEHOLD"]);

export function tenureKey(listing) {
  return KNOWN_TENURES.has(listing.tenure) ? listing.tenure : "UNKNOWN";
}

// epc_current is stored "<letter> (<score>)"; match on the letter only.
export function epcBand(listing) {
  const m = /^\s*([A-G])\b/i.exec(listing.epc_current || "");
  return m ? m[1].toUpperCase() : null;
}

export function deriveOptions(listings) {
  const tenure = {};
  const epc = {};
  let chainFree = 0;
  for (const l of listings) {
    const t = tenureKey(l);
    tenure[t] = (tenure[t] || 0) + 1;
    const band = epcBand(l);
    if (band) epc[band] = (epc[band] || 0) + 1;
    if (l.chain_free === true) chainFree += 1;
  }
  return { tenure, epc, chainFree };
}

// Options to render, in fixed order: every value that exists, plus any
// currently-selected value whose last listing vanished (count 0, greyed so
// it can still be cleared).
export function visibleOptions(options, filters) {
  const tenure = TENURE_OPTIONS.filter((o) => options.tenure[o.value] || filters.tenure.includes(o.value)).map(
    (o) => ({ ...o, count: options.tenure[o.value] || 0 })
  );
  const epc = EPC_BANDS.filter((b) => options.epc[b] || filters.epc.includes(b)).map((b) => ({
    value: b,
    label: b,
    count: options.epc[b] || 0,
  }));
  const showChainFree = options.chainFree > 0 || filters.chainFree;
  return { tenure, epc, showChainFree, chainFreeCount: options.chainFree };
}

// AND between groups, OR within a group.
export function applyFilters(listings, filters) {
  return listings.filter((l) => {
    if (filters.tenure.length && !filters.tenure.includes(tenureKey(l))) return false;
    if (filters.epc.length && !filters.epc.includes(epcBand(l))) return false;
    if (filters.chainFree && l.chain_free !== true) return false;
    return true;
  });
}

export function activeFilterCount(filters) {
  return filters.tenure.length + filters.epc.length + (filters.chainFree ? 1 : 0);
}

const present = (v) => v !== null && v !== undefined && v !== 0;

// Missing values go last in both directions.
function byNumber(field, dir) {
  return (a, b) => {
    const av = present(a[field]);
    const bv = present(b[field]);
    if (!av && !bv) return 0;
    if (!av) return 1;
    if (!bv) return -1;
    return dir * (a[field] - b[field]);
  };
}

export function sortListings(listings, sortBy) {
  const copy = [...listings];
  if (sortBy === "price_asc") return copy.sort(byNumber("price_gbp", 1));
  if (sortBy === "price_desc") return copy.sort(byNumber("price_gbp", -1));
  if (sortBy === "size_asc") return copy.sort(byNumber("floor_area_sqft", 1));
  if (sortBy === "size_desc") return copy.sort(byNumber("floor_area_sqft", -1));
  return copy.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
}

export function toggleIn(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}
