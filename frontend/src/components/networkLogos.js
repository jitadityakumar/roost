// Trademark-protected network logos aren't committed to this public repo
// (see .gitignore) — glob resolves to {} when the files are absent, so a
// fresh clone / the public build falls back to letter badges (see
// NearestStations.jsx's TYPE_BADGES) with no build error and no manual
// step. Kept in its own module (not inlined in NearestStations.jsx) so
// tests can vi.mock() a deterministic result instead of depending on
// whether these gitignored files happen to be present on the dev machine
// running the test.
const LOGO_MODULES = import.meta.glob("../assets/network-logos/*.svg", {
  eager: true,
  query: "?url",
  import: "default",
});

const LOGO_FILES = {
  LONDON_UNDERGROUND: "underground.svg",
  LONDON_OVERGROUND: "overground.svg",
  ELIZABETH_LINE: "elizabeth-line.svg",
  LIGHT_RAILWAY: "dlr.svg",
  TRAM: "tram.svg",
  NATIONAL_TRAIN: "national-rail.svg",
};

export function logoUrlForType(type) {
  const filename = LOGO_FILES[type];
  return filename ? LOGO_MODULES[`../assets/network-logos/${filename}`] : undefined;
}
