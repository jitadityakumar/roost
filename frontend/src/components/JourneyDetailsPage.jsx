import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import { logoUrlForType } from "./networkLogos.js";

// Leg badges are keyed by TfL leg `mode.id` values (national-rail, tube,
// walking, ...) -- a different key space than NearestStations.jsx's
// TYPE_BADGES (Rightmove's nearest_stations_raw[].types). Mapped to the
// equivalent Rightmove type below so the real logo files NearestStations.jsx
// already uses (gitignored, see networkLogos.js) get reused for free when
// present; the colored-letter fallback (same style as TYPE_BADGES) only
// applies when a logo file for the type isn't on disk.
const LEG_BADGES = {
  tube: { letter: "U", bg: "#E32017", rightmoveType: "LONDON_UNDERGROUND" },
  overground: { letter: "O", bg: "#EE7C0E", rightmoveType: "LONDON_OVERGROUND" },
  "elizabeth-line": { letter: "E", bg: "#7156A5", rightmoveType: "ELIZABETH_LINE" },
  dlr: { letter: "D", bg: "#00A4A7", rightmoveType: "LIGHT_RAILWAY" },
  tram: { letter: "T", bg: "#84B817", rightmoveType: "TRAM" },
  "national-rail": { letter: "R", bg: "#003088", rightmoveType: "NATIONAL_TRAIN" },
};

function legBadge(mode) {
  return LEG_BADGES[mode] || { letter: "?", bg: "#666", rightmoveType: null };
}

function formatClock(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

// "45m" under an hour, "2h" for an exact number of hours, "1h 18m" otherwise.
function formatDuration(totalMinutes) {
  if (totalMinutes == null) return "";
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h ${minutes}m`;
}

// query_params.date is "YYYYMMDD", .time is "HHMM" -- the original target
// date/time the destination was searched for, not any leg's actual clock
// time.
function formatTargetDateTime(dateStr, timeStr) {
  if (!dateStr || !timeStr) return "";
  const year = dateStr.slice(0, 4);
  const month = dateStr.slice(4, 6);
  const day = dateStr.slice(6, 8);
  const hour = timeStr.slice(0, 2);
  const minute = timeStr.slice(2, 4);
  const d = new Date(`${year}-${month}-${day}T${hour}:${minute}:00`);
  if (Number.isNaN(d.getTime())) return `${dateStr} ${timeStr}`;
  return `${d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" })}, ${hour}:${minute}`;
}

function formatFetchedAt(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleString([], { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Leg({ leg }) {
  const isWalk = leg.mode === "walking";
  const badge = legBadge(leg.mode);
  const logoUrl = !isWalk && badge.rightmoveType ? logoUrlForType(badge.rightmoveType) : undefined;
  return (
    <div className="jd-leg">
      {logoUrl ? (
        <img className="jd-leg-badge jd-leg-badge-logo" src={logoUrl} alt="" title={leg.operator || undefined} />
      ) : (
        <span className={`jd-leg-badge${isWalk ? " jd-leg-badge-walk" : ""}`} style={isWalk ? undefined : { background: badge.bg }}>
          {isWalk ? "W" : badge.letter}
        </span>
      )}
      <div className="jd-leg-info">
        <span className="jd-leg-op">{isWalk ? "Walk" : leg.operator || "—"}</span>
        <span className="jd-leg-route">
          {leg.from} → {leg.to}
        </span>
      </div>
      <div className="jd-leg-time">
        <span className="jd-leg-clock">
          {formatClock(leg.departure_time)}–{formatClock(leg.arrival_time)}
        </span>
        <span className="jd-leg-dur">{leg.duration != null ? `${leg.duration}m` : ""}</span>
      </div>
    </div>
  );
}

function CandidateRow({ candidate }) {
  const changeLabel =
    candidate.kind === "direct"
      ? "direct"
      : `${candidate.num_changes} change${candidate.num_changes === 1 ? "" : "s"}`;

  return (
    <details className="jd-candidate">
      <summary>
        <span className="jd-chevron" aria-hidden="true">▸</span>
        <span className="jd-candidate-time">
          {formatClock(candidate.start_time)} → {formatClock(candidate.arrival_time)}
        </span>
        <span className="jd-candidate-meta">
          {formatDuration(candidate.duration_minutes)} · {changeLabel}
        </span>
      </summary>
      <div className="jd-legs">
        {candidate.legs.map((leg, i) => (
          <div key={i}>
            <Leg leg={leg} />
            {leg.change_minutes != null && (
              <div className="jd-change">{`${leg.change_minutes}m change`}</div>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

export default function JourneyDetailsPage() {
  const { poolId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api
      .journeyScanPool(poolId)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [poolId]);

  if (error) {
    return (
      <div className="journey-details-page">
        <p className="error">Couldn't load journey details: {error}</p>
      </div>
    );
  }

  if (data === null) {
    return (
      <div className="journey-details-page">
        <p>Loading…</p>
      </div>
    );
  }

  return (
    <div className="journey-details-page">
      <div className="jd-header">
        <h2>{data.destination_name}</h2>
        <div className="jd-header-meta">
          <span>
            Journey for <strong>{formatTargetDateTime(data.query_params.date, data.query_params.time)}</strong>
          </span>
          <span>
            Fetched <strong>{formatFetchedAt(data.scanned_at)}</strong>
          </span>
        </div>
      </div>

      {data.candidates.length === 0 ? (
        <p className="empty-state">No candidate journeys stored for this scan.</p>
      ) : (
        <div className="jd-candidates">
          {data.candidates.map((candidate, i) => (
            <CandidateRow key={i} candidate={candidate} />
          ))}
        </div>
      )}

      <div className="jd-footer">
        <div className="jd-footer-row">
          <span className="jd-footer-label">journeyPreference</span>
          <span className="jd-footer-val">{data.query_params.journeyPreference}</span>
        </div>
        <div className="jd-footer-row">
          <span className="jd-footer-label">mode</span>
          <span className="jd-footer-val">{data.query_params.mode}</span>
        </div>
      </div>
    </div>
  );
}
