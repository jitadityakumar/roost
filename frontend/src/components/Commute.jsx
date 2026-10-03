import { useEffect, useState } from "react";
import { api } from "../api.js";
import { formatDistance } from "./NearestStations.jsx";
import LineBadge from "./LineBadge.jsx";
import { operatorNames } from "../lineBadges.js";
import { formatWalkMeters, walkDurationClass } from "./walkFormat.js";

// "18–22" -> "18m-22m"
function formatRange(range) {
  return range ? range.replace(/[-–]/, "m-") + "m" : null;
}

// "5–6" -> "5-6 stops"
function formatStops(range) {
  return range ? `${range.replace(/[-–]/, "-")} stops` : null;
}

function statsFor(t) {
  return [
    `${t.journey_time_mins}m`,
    `${t.trains_per_hour}/hr`,
    formatRange(t.journey_range),
    formatStops(t.stops_range),
  ]
    .filter(Boolean)
    .join(" · ");
}

// One row per terminus with its peak and off-peak figures side by side.
// Pairs by primary terminus code (not position or the also-calls-at
// grouping), follows the peak order, and appends any off-peak-only termini.
// A missing side is null -- the row renders "No peak" / "No off-peak" for it.
export function mergeTermini(termini) {
  const peak = termini?.peak?.termini ?? [];
  const offpeak = termini?.offpeak?.termini ?? [];
  const offByCrs = new Map(offpeak.map((t) => [t.terminus_crs, t]));
  const rows = peak.map((p) => ({ peak: p, offpeak: offByCrs.get(p.terminus_crs) ?? null }));
  const peakCrs = new Set(peak.map((t) => t.terminus_crs));
  offpeak.filter((o) => !peakCrs.has(o.terminus_crs)).forEach((o) => rows.push({ peak: null, offpeak: o }));
  return rows;
}

function TerminusRow({ row }) {
  // Identity (name, badges, also-calls-at) is the same on both sides when
  // both exist; fall back to whichever side is present.
  const base = row.peak ?? row.offpeak;

  return (
    <li className="commute-terminus-row">
      <div className="commute-terminus-line1">
        <span className="commute-terminus-name">
          {base.terminus_name}
          {base.also_calls_at?.length > 0 && (
            <span className="commute-also-calls-at">
              {" "}
              (also to {base.also_calls_at.map((t) => t.terminus_name).join(", ")})
            </span>
          )}
        </span>
        <span className="commute-terminus-stats">
          {row.peak ? `Peak: ${statsFor(row.peak)}` : "No peak"}
        </span>
      </div>
      <div className="commute-terminus-line2">
        <span className="commute-terminus-badges">
          {(base.tube_lines || []).map((tl) => (
            <LineBadge key={`line-${tl.line}`} name={tl.line} color={tl.color} />
          ))}
          {operatorNames(base.operators_title).map((op) => (
            <LineBadge key={`op-${op}`} name={op} />
          ))}
        </span>
        <span className="commute-terminus-stats">
          {row.offpeak ? `Off-peak: ${statsFor(row.offpeak)}` : "No off-peak"}
        </span>
      </div>
    </li>
  );
}

function TerminusList({ termini }) {
  const rows = mergeTermini(termini);
  if (rows.length === 0) return null;
  return (
    <ul className="commute-terminus-list">
      {rows.map((r) => (
        <TerminusRow key={(r.peak ?? r.offpeak).terminus_crs} row={r} />
      ))}
    </ul>
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
        <TerminusList termini={station.termini} />
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
