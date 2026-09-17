// Mirrors backend/app/field_colors/fields.py -- the six fields eligible for
// admin-configured green/amber/red colour coding (issue #100). chain_free is
// deliberately absent: its highlight is a hard-coded frontend conditional,
// not an admin rule.
export const COLORABLE_NUMERIC_FIELDS = {
  price_gbp: "Price",
  lease_years_remaining: "Lease years remaining",
  service_charge_pa: "Service charge (per yr)",
  floor_area_sqft: "Floor area (sq ft)",
  broadband_top_speed_mbps: "Broadband top speed",
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
];

export const EPC_BANDS = ["A", "B", "C", "D", "E", "F", "G"];

export function colorableFieldKind(field) {
  if (field in COLORABLE_NUMERIC_FIELDS) return "numeric";
  if (field in COLORABLE_EPC_BAND_FIELDS) return "epc_band";
  return null;
}
