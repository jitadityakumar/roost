// Single source for line / operator badge data (issue #98). Edit colours here
// when operators rebrand. Names match what TfL and london-commuter-stations
// return (e.g. "Waterloo & City", "South Western Railway").
//
// group -> shape on the small tile and which logo the large tile shows:
//   underground: rectangle, 3-letter code
//   overground | elizabeth | dlr | tram: pill, 3-letter code
//   rail: circle, 2-letter National Rail operator code
// logoType is a networkLogos.js key (the logo files are gitignored).
const GROUP_LOGO_TYPE = {
  underground: "LONDON_UNDERGROUND",
  overground: "LONDON_OVERGROUND",
  elizabeth: "ELIZABETH_LINE",
  dlr: "LIGHT_RAILWAY",
  tram: "TRAM",
  rail: "NATIONAL_TRAIN",
};

const UNDERGROUND = [
  ["Bakerloo", "BAK", "#B36305"],
  ["Central", "CEN", "#E32017"],
  ["Circle", "CIR", "#FFD300"],
  ["District", "DIS", "#00782A"],
  ["Hammersmith & City", "H&C", "#F3A9BB"],
  ["Jubilee", "JUB", "#A0A5A9"],
  ["Metropolitan", "MET", "#9B0056"],
  ["Northern", "NOR", "#000000"],
  ["Piccadilly", "PIC", "#003688"],
  ["Victoria", "VIC", "#0098D4"],
  ["Waterloo & City", "W&C", "#95CDBA"],
];

const OVERGROUND = [
  ["Lioness", "LIO", "#FFA32B"],
  ["Mildmay", "MIL", "#0071CE"],
  ["Windrush", "WIN", "#ED1B00"],
  ["Weaver", "WEA", "#9B1F5E"],
  ["Suffragette", "SUF", "#18A95D"],
  ["Liberty", "LIB", "#676767"],
];

const OTHER_TFL = [
  ["Elizabeth line", "ELI", "#6950A1", "elizabeth"],
  ["DLR", "DLR", "#00A4A7", "dlr"],
  ["Tram", "TRM", "#84B817", "tram"],
];

// [name, official National Rail code, colour]. LM is shared by two operators.
const RAIL = [
  ["Southeastern", "SE", "#389CFF"],
  ["Thameslink", "TL", "#FF5AA4"],
  ["Southern", "SN", "#8CC63E"],
  ["South Western Railway", "SW", "#24398C"],
  ["Great Northern", "GN", "#0099FF"],
  ["Greater Anglia", "LE", "#D70428"],
  ["c2c", "CC", "#B7007C"],
  ["Great Western Railway", "GW", "#0A493E"],
  ["London Northwestern Railway", "LM", "#00BF6F"],
  ["West Midlands Railway", "LM", "#FF8300"],
  ["Chiltern Railways", "CH", "#00BFFF"],
  ["Gatwick Express", "GX", "#EB1E2D"],
  ["Heathrow Express", "HX", "#532E63"],
  ["East Midlands Railway", "EM", "#713563"],
  ["Avanti West Coast", "VT", "#004354"],
  ["London North Eastern Railway", "GR", "#D70E35"],
  ["Lumo", "LD", "#2B6EF5"],
];

export const LINE_BADGES = [
  ...UNDERGROUND.map(([name, code, color]) => ({ name, code, color, group: "underground" })),
  ...OVERGROUND.map(([name, code, color]) => ({ name, code, color, group: "overground" })),
  ...OTHER_TFL.map(([name, code, color, group]) => ({ name, code, color, group })),
  ...RAIL.map(([name, code, color]) => ({ name, code, color, group: "rail" })),
].map((b) => ({ ...b, logoType: GROUP_LOGO_TYPE[b.group] }));

// Alternate spellings seen in london-commuter-stations data -> canonical name.
const ALIASES = {
  "elizabeth line": "Elizabeth line",
};

// The data source sometimes merges two operators into one name; show both.
const COMBINED = {
  "lnr & wmr": ["London Northwestern Railway", "West Midlands Railway"],
};

// "South Western Railway, Southeastern" (comma-joined operators_title) ->
// ["South Western Railway", "Southeastern"], combined names expanded.
export function operatorNames(title) {
  return (title || "")
    .split(", ")
    .map((n) => n.trim())
    .filter(Boolean)
    .flatMap((n) => COMBINED[n.toLowerCase()] ?? [n]);
}

const BY_NAME = new Map(LINE_BADGES.map((b) => [b.name.toLowerCase(), b]));

const FALLBACK_COLOR = "#888888";

// Unknown names (e.g. "London Overground", CrossCountry) get a neutral pill
// tile with no logo, so nothing silently disappears or borrows a wrong
// network's logo. `color` overrides the table (Commute passes the API's
// own line colour).
export function lookupLineBadge(name, color) {
  const key = String(name || "").trim().toLowerCase();
  const found = BY_NAME.get(ALIASES[key]?.toLowerCase() ?? key);
  const badge = found ?? {
    name: String(name || "").trim(),
    code: String(name || "?").trim().slice(0, 3).toUpperCase() || "?",
    color: FALLBACK_COLOR,
    group: "other",
    logoType: undefined,
  };
  return color ? { ...badge, color } : badge;
}

// Tube/Overground/etc. tiles keep Commute's original luminance rule; rail
// tiles use WCAG contrast (Commute's rule is weak on several rail colours).
function channel(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function parseHex(hex) {
  const h = (hex || "").replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.substring(i, i + 2), 16));
}

export function luminanceText(hex) {
  if (!hex) return "#fff";
  const [r, g, b] = parseHex(hex);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? "#000" : "#fff";
}

export function wcagText(hex) {
  const [r, g, b] = parseHex(hex);
  const lum = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  // contrast vs white = 1.05 / (lum + 0.05); vs black = (lum + 0.05) / 0.05
  return 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05 ? "#fff" : "#000";
}

export function textColorFor(badge) {
  return badge.group === "rail" ? wcagText(badge.color) : luminanceText(badge.color);
}
