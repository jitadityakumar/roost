// Mirrors backend/app/field_colors/fields.py -- the fields eligible for
// admin-configured green/amber/red colour coding (issue #100, plus
// crime_multiplier/initial_monthly_payment added for issue #101). chain_free
// is deliberately absent: its highlight is a hard-coded frontend conditional,
// not an admin rule.
//
// Unlike the other fields, crime_multiplier and initial_monthly_payment
// aren't `listings` columns -- the server's field_colors.evaluate never
// colours them (nothing in listing.field_colors for these keys). They're
// evaluated client-side instead, via numericColorFor below, against the same
// threshold rows fetched from /api/admin/field-color-thresholds.
export const COLORABLE_NUMERIC_FIELDS = {
  price_gbp: "Price",
  lease_years_remaining: "Lease years remaining",
  service_charge_pa: "Service charge (per yr)",
  floor_area_sqft: "Floor area (sq ft)",
  broadband_top_speed_mbps: "Broadband top speed",
  crime_multiplier: "Crime multiplier",
  initial_monthly_payment: "Initial monthly payment",
};

export const COLORABLE_EPC_BAND_FIELDS = {
  epc_current: "EPC current",
};

export const COLORABLE_FIELD_LABELS = { ...COLORABLE_NUMERIC_FIELDS, ...COLORABLE_EPC_BAND_FIELDS };

// Display order for the admin panel -- matches the issue's field list order.
export const COLORABLE_FIELD_ORDER = [
  "price_gbp",
  "lease_years_remaining",
  "service_charge_pa",
  "floor_area_sqft",
  "epc_current",
  "broadband_top_speed_mbps",
  "crime_multiplier",
  "initial_monthly_payment",
];

export const EPC_BANDS = ["A", "B", "C", "D", "E", "F", "G"];

export function colorableFieldKind(field) {
  if (field in COLORABLE_NUMERIC_FIELDS) return "numeric";
  if (field in COLORABLE_EPC_BAND_FIELDS) return "epc_band";
  return null;
}

// Client-side mirror of backend/app/field_colors/evaluate.py's numeric
// branch, for the two fields (crime_multiplier, initial_monthly_payment)
// that never reach the server's colors_for_listing since they aren't
// `listings` columns -- see the comment above COLORABLE_NUMERIC_FIELDS.
// Cutoffs inclusive at both ends, red checked before green, same as the
// backend. `rule` is a raw row from api.fieldColors.list() ({field,
// green_cutoff, red_cutoff, higher_is_better}) or undefined/null.
export function numericColorFor(value, rule) {
  if (rule == null || value == null) return null;
  const lv = Number(value);
  if (Number.isNaN(lv)) return null;

  const toNumber = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
  const green = toNumber(rule.green_cutoff);
  const red = toNumber(rule.red_cutoff);
  const higherIsBetter = Boolean(rule.higher_is_better);

  if (red !== null && ((higherIsBetter && lv <= red) || (!higherIsBetter && lv >= red))) return "red";
  if (green !== null && ((higherIsBetter && lv >= green) || (!higherIsBetter && lv <= green))) return "green";
  return "amber";
}
