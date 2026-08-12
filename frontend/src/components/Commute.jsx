import { useEffect, useState } from "react";
import { api } from "../api.js";
import { formatDistance } from "./NearestStations.jsx";

// Line colors come from the API as arbitrary hex, so text color needs to be
// picked for contrast rather than hardcoded (unlike NearestStations' fixed
// badge palette).
function contrastText(hexColor) {
  if (!hexColor) return "#fff";
  const hex = hexColor.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#000" : "#fff";
}

// "18–22" -> "18m-22m"
function formatRange(range) {
  return range ? range.replace(/[-–]/, "m-") + "m" : null;
}

// "5–6" -> "5-6 stops"
function formatStops(range) {
  return range ? `${range.replace(/[-–]/, "-")} stops` : null;
}

function TerminusRow({ terminus }) {
  const stats = [
    `${terminus.journey_time_mins}m`,
    `${terminus.trains_per_hour}/hr`,
    formatRange(terminus.journey_range),
    formatStops(terminus.stops_range),
  ].filter(Boolean);

  return (
    <li className="commute-terminus-row">
      <div className="commute-terminus-line1">
        <span className="commute-terminus-name">
          {terminus.terminus_name}
          {terminus.also_calls_at?.length > 0 && (
            <span className="commute-also-calls-at">
              {" "}
              (also to {terminus.also_calls_at.map((t) => t.terminus_name).join(", ")})
            </span>
          )}
        </span>
        <span className="commute-terminus-stats">{stats.join(" · ")}</span>
      </div>
      <div className="commute-terminus-line2">
        <span className="commute-terminus-tube-lines">
          {(terminus.tube_lines || []).map((tl) => (
            <span
              key={tl.line}
              className="tube-line-badge"
              style={{ backgroundColor: tl.color, color: contrastText(tl.color) }}
            >
              {tl.line}
            </span>
          ))}
        </span>
        <span className="commute-terminus-operator">{terminus.operators_title}</span>
      </div>
    </li>
  );
}

function TerminusList({ label, group }) {
  if (!group || group.termini.length === 0) return null;
  return (
    <div className="commute-terminus-group">
      <h5>{label}</h5>
      <ul className="commute-terminus-list">
        {group.termini.map((t) => (
          <TerminusRow key={t.terminus_crs} terminus={t} />
        ))}
      </ul>
    </div>
  );
}

const METERS_PER_MILE = 1609.344;

// Same good/warn/bad tier convention as the crime-baseline badges
// (badge-crime-good/warn/bad in index.css).
function walkDurationClass(minutes) {
  if (minutes <= 10) return "station-walk-duration-good";
  if (minutes <= 20) return "station-walk-duration-warn";
  return "station-walk-duration-bad";
}

function StationCommute({ station }) {
  const walkDistanceMiles =
    station.walk_distance_meters != null ? station.walk_distance_meters / METERS_PER_MILE : null;
  const distanceLabel = formatDistance(walkDistanceMiles ?? station.distance);
  const walkMinutes =
    station.walk_duration_seconds != null ? Math.round(station.walk_duration_seconds / 60) : null;
  const walkClass = walkMinutes != null ? `station-walk-duration ${walkDurationClass(walkMinutes)}` : null;

  return (
    <div className="commute-station">
      <h4>
        {station.name}{" "}
        {distanceLabel && <span className="station-distance">({distanceLabel})</span>}
        {walkMinutes != null &&
          (station.walk_maps_url ? (
            <a className={walkClass} href={station.walk_maps_url} target="_blank" rel="noreferrer">
              {" "}
              · {walkMinutes} min walk ↗
            </a>
          ) : (
            <span className={walkClass}> · {walkMinutes} min walk</span>
          ))}
      </h4>
      {station.error && <p className="error">Couldn't load commute times for this station.</p>}
      {station.termini && (
        <>
          <TerminusList label="Peak" group={station.termini.peak} />
          <TerminusList label="Off-peak" group={station.termini.offpeak} />
        </>
      )}
    </div>
  );
}

export default function Commute({ listingId, ready }) {
  const [stations, setStations] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setStations(null);
    setError(null);
    api
      .commute(listingId)
      .then((data) => {
        if (!cancelled) setStations(data.stations);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [listingId, ready]);

  if (!ready) return <p className="coming-soon">Waiting for listing details…</p>;
  if (error) return <p className="error">Couldn't load commute times: {error}</p>;
  if (stations === null) return <p>Loading…</p>;
  if (stations.length === 0) {
    return <p className="coming-soon">No nearby National Rail stations found.</p>;
  }

  return (
    <div className="commute-stations">
      {stations.map((s) => (
        <StationCommute key={s.crs} station={s} />
      ))}
    </div>
  );
}
