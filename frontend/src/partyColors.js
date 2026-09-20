// Party colours for the Local Politics section (issue #61). Values are
// Parliament's own (Members API `backgroundColour`); the seat bar needs a
// Roost-side map keyed by the council CSV's party columns, since that CSV has
// no colours. UKIP and Other have no Parliament value -> neutral grey. Light/
// dark variants for Labour/Conservative/Lib Dem live in index.css as
// --party-* custom properties (our own dark-mode adjustments, not Parliament
// values).
export const PARTY_COLOR_VAR = {
  con: "var(--party-con)",
  lab: "var(--party-lab)",
  ld: "var(--party-ld)",
  green: "var(--party-green)",
  ref: "var(--party-ref)",
  snp: "var(--party-snp)",
  pc: "var(--party-pc)",
  ukip: "var(--party-neutral)",
  other: "var(--party-neutral)",
};

export const PARTY_SHORT = {
  con: "Con",
  lab: "Lab",
  ld: "LD",
  green: "Grn",
  ref: "Ref",
  snp: "SNP",
  pc: "PC",
  ukip: "UKIP",
  other: "Oth",
};

export const NEUTRAL_GREY = "#909090";

export function partyColor(key) {
  return PARTY_COLOR_VAR[key] || "var(--party-neutral)";
}

// Black or white text for a hex background (SNP's #fff685 is near-white).
export function readableTextColor(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "#fff";
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#1a1a1a" : "#fff";
}
