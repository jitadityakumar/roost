import { formatWalkMeters, walkDurationClass } from "./walkFormat.js";
import { logoUrlForType } from "./networkLogos.js";

// Colored letter badges identify each network without reproducing its
// trademarked logo (TfL roundel, National Rail double-arrow, etc.) in this
// public repo. Real logo files, when present, are gitignored and live at
// ../assets/network-logos/ (see LOGO_FILES below) — this is the fallback
// used whenever a logo file for the type isn't on disk.
//
// Keys are Rightmove's real `nearest_stations_raw[].types` values, pinned
// against actual observed data (backend/app/jobs/handlers.py's
// _TFL_MODE_BY_TYPE has the same mapping) — NOT guesses. Two were wrong
// until issue #44: DLR stations are typed "LIGHT_RAILWAY", not "DLR", and
// tram stops are typed "TRAM", not "TRAMLINK" — both silently fell through
// to DEFAULT_TYPE_BADGE below instead of matching.
const TYPE_BADGES = {
  LONDON_UNDERGROUND: { letter: "U", label: "Underground", bg: "#E32017" },
  LONDON_OVERGROUND: { letter: "O", label: "Overground", bg: "#EE7C0E" },
  ELIZABETH_LINE: { letter: "E", label: "Elizabeth line", bg: "#7156A5" },
  LIGHT_RAILWAY: { letter: "D", label: "DLR", bg: "#00A4A7" },
  TRAM: { letter: "T", label: "Tram", bg: "#84B817" },
  NATIONAL_TRAIN: { letter: "R", label: "National Rail", bg: "#003088" },
};
const DEFAULT_TYPE_BADGE = { letter: "?", label: "Station", bg: "#666" };

export function formatDistance(distance, unit) {
  const n = Number(distance);
  if (distance === null || distance === undefined || Number.isNaN(n)) return null;
  return `${n.toFixed(2)} ${unit || "mi"}`;
}

export default function NearestStations({ stations }) {
  if (!Array.isArray(stations) || stations.length === 0) return null;

  return (
    <ul className="station-list">
      {stations.map((s, i) => {
        const hasWalkData = s.walk_distance_meters != null && s.walk_duration_seconds != null;
        const walkMinutes = hasWalkData ? Math.round(s.walk_duration_seconds / 60) : null;

        return (
          <li key={`${s.name}-${i}`} className="station-row">
            <span className="station-icons">
              {(Array.isArray(s.types) && s.types.length > 0 ? s.types : ["_"]).map((t, j) => {
                const { letter, label, bg } = TYPE_BADGES[t] || DEFAULT_TYPE_BADGE;
                const logoUrl = logoUrlForType(t);
                if (logoUrl) {
                  return (
                    <img
                      key={`${t}-${j}`}
                      className="station-badge station-badge-logo"
                      src={logoUrl}
                      title={label}
                      alt={label}
                    />
                  );
                }
                return (
                  <span
                    key={`${t}-${j}`}
                    className="station-badge"
                    style={{ backgroundColor: bg }}
                    role="img"
                    title={label}
                    aria-label={label}
                  >
                    {letter}
                  </span>
                );
              })}
            </span>
            <span className="station-name">{s.name}</span>
            <span className="station-distance-wrap">
              {hasWalkData && (
                <span className={`station-walk-duration ${walkDurationClass(walkMinutes)}`}>
                  {formatWalkMeters(s.walk_distance_meters)} · {walkMinutes} min walk
                </span>
              )}
              <span
                className="station-distance"
                title="As the crow flies (Rightmove data)"
                aria-label={`As the crow flies: ${formatDistance(s.distance, s.unit)}`}
              >
                {formatDistance(s.distance, s.unit)}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
