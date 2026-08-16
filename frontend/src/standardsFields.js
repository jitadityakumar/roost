// Mirrors backend/app/standards/fields.py -- single source of truth for the
// admin page's field dropdown, kept in sync with the labels ListingDetail
// already shows for these same columns.
export const NUMERIC_FIELDS = {
  price_gbp: "Price",
  bedrooms: "Bedrooms",
  bathrooms: "Bathrooms",
  lease_years_remaining: "Lease years remaining",
  service_charge_pa: "Service charge (per yr)",
  service_charge_pm: "Service charge (per mo)",
  floor_area_sqft: "Floor area (sq ft)",
  // Computed, not a raw listing column -- see backend/app/standards/fields.py.
  // Value is in minutes, not seconds.
  min_walk_minutes: "Walking time to nearest station (min)",
};

export const BOOLEAN_FIELDS = {
  cash_only: "Cash buyers only",
  chain_free: "Chain free",
  garden: "Garden",
};

// epc_current is stored as "<letter> (<score>)" (e.g. "C (73)") -- rules
// compare on the letter band only. Bands already sort correctly as plain
// characters (A best .. G worst), so lt/gt read naturally as "better than"
// / "worse than".
export const EPC_BAND_FIELDS = {
  epc_current: "EPC current",
};
export const EPC_BANDS = ["A", "B", "C", "D", "E", "F", "G"];

export const FIELD_LABELS = { ...NUMERIC_FIELDS, ...BOOLEAN_FIELDS, ...EPC_BAND_FIELDS };

export const NUMERIC_OPERATORS = [
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "eq", label: "=" },
  { value: "neq", label: "≠" },
];

export const BOOLEAN_OPERATORS = [
  { value: "eq", label: "=" },
  { value: "neq", label: "≠" },
];

export const EPC_BAND_OPERATORS = NUMERIC_OPERATORS;

export function fieldType(field) {
  if (field in NUMERIC_FIELDS) return "numeric";
  if (field in BOOLEAN_FIELDS) return "boolean";
  if (field in EPC_BAND_FIELDS) return "epc_band";
  return null;
}
