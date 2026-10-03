import { useEffect, useState } from "react";
import { api } from "../api.js";
import { formatDistance } from "./NearestStations.jsx";
import LineBadge from "./LineBadge.jsx";
import { formatWalkMeters, walkDurationClass } from "./walkFormat.js";

// "18–22" -> "18m-22m"
function formatRange(range) {
  return range ? range.replace(/[-–]/, "m-") + "m" : null;
}

// "5–6" -> "5-6 stops"
function formatStops(range) {
  return range ? `${range.replace(/[-–]/, "-")} stops` : null;
}

// "South Western Railway, Southeastern" -> ["South Western Railway", "Southeastern"]
function operatorNames(title) {
  return (title || "").split(", ").filter(Boolean);
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
        <span className="commute-terminus-badges">
          {(terminus.tube_lines || []).map((tl) => (
            <LineBadge key={tl.line} name={tl.line} />
          ))}
        </span>
        <span className="commute-terminus-badges">
          {operatorNames(terminus.operators_title).map((op) => (
            <LineBadge key={op} name={op} />
          ))}
        </span>
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

function StationCommute({ station }) {
  const hasWalkData = station.walk_distance_meters != null && station.walk_duration_seconds != null;
  const walkMinutes = hasWalkData ? Math.round(station.walk_duration_seconds / 60) : null;
  const walkLabel = hasWalkData
    ? `${formatWalkMeters(station.walk_distance_meters)} · ${walkMinutes} min walk`
    : null;
  const walkClass = walkMinutes != null ? `station-walk-duration ${walkDurationClass(walkMinutes)}` : null;
  const fallbackDistanceLabel = hasWalkData ? null : formatDistance(station.distance);

  return (
    <div className="commute-station">
      <h4>
        {station.name}{" "}
        {walkLabel &&
          (station.walk_maps_url ? (
            <a className={walkClass} href={station.walk_maps_url} target="_blank" rel="noreferrer">
              ({walkLabel}) ↗
            </a>
          ) : (
            <span className={walkClass}>({walkLabel})</span>
          ))}
        {fallbackDistanceLabel && <span className="station-distance">({fallbackDistanceLabel})</span>}
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
