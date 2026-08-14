// Shared by Commute.jsx and NearestStations.jsx so both render walk
// distance/duration identically -- see context.md's "Station walking
// distance" section.

// 845 -> "845m", 1250 -> "1.3km" -- meters below 1km, one-decimal km above,
// matching how Google Maps itself switches units.
export function formatWalkMeters(meters) {
  return meters < 1000 ? `${Math.round(meters)}m` : `${(meters / 1000).toFixed(1)}km`;
}

// Same good/warn/bad tier convention as the crime-baseline badges
// (badge-crime-good/warn/bad in index.css).
export function walkDurationClass(minutes) {
  if (minutes <= 7) return "station-walk-duration-good";
  if (minutes <= 15) return "station-walk-duration-warn";
  return "station-walk-duration-bad";
}
