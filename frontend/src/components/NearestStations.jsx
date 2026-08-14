import { formatWalkMeters, walkDurationClass } from "./walkFormat.js";

// Brand colors identify each network without reproducing its trademarked
// logo (TfL roundel, National Rail double-arrow, etc.) in the repo.
const TYPE_BADGES = {
  LONDON_UNDERGROUND: { letter: "U", label: "Underground", bg: "#E32017" },
  LONDON_OVERGROUND: { letter: "O", label: "Overground", bg: "#EE7C0E" },
  ELIZABETH_LINE: { letter: "E", label: "Elizabeth line", bg: "#7156A5" },
  DLR: { letter: "D", label: "DLR", bg: "#00A4A7" },
  TRAMLINK: { letter: "T", label: "Tram", bg: "#84B817" },
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
              <span className="station-distance" title="As the crow flies (Rightmove data)">
                {formatDistance(s.distance, s.unit)}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
