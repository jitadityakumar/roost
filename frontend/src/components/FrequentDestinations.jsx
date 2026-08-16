import { useEffect, useState } from "react";
import { api } from "../api.js";

// "45m" under an hour, "2h" for an exact number of hours, "1h6m" otherwise
// -- rather than a bare minute count.
function formatDuration(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes}m`;
  if (minutes === 0) return `${hours}h`;
  return `${hours}h${minutes}m`;
}

function DestinationRow({ destination }) {
  if (!destination.resolved) {
    return (
      <li className="destination-row">
        <div className="destination-line1">
          <span className="destination-name">{destination.name}</span>
        </div>
        <div className="destination-unresolved">
          No journey found for {destination.day_label.slice(0, 3)} {destination.time}
          {destination.destination_type === "postcode" ? ` (${destination.station_name})` : ""}.
        </div>
      </li>
    );
  }

  // Postcode-type destinations show the resolved StationFrom -> StationTo
  // once a journey exists (not the raw postcode, which is only useful
  // before resolution -- see destination.resolved above) -- matches how
  // station-type destinations already displayed. The row label is a plain
  // change count, no "(via X, Y)" station-name suffix -- a leg-by-leg
  // breakdown isn't buildable from what's stored (issue #47 UX addendum).
  const routeLabel =
    destination.kind === "direct"
      ? "direct"
      : `${destination.num_changes} change${destination.num_changes === 1 ? "" : "s"}`;

  return (
    <li className="destination-row">
      <div className="destination-line1">
        <span className="destination-name">
          {destination.name}{" "}
          <span className="destination-station">
            · {destination.origin_name} → {destination.arrival_name}
          </span>
        </span>
        <span className="destination-duration good">{formatDuration(destination.duration_minutes)}</span>
      </div>
      <div className="destination-line2">
        <span className="destination-target">
          {destination.day_label.slice(0, 3)} {destination.time}
        </span>
        <span className="destination-route">{routeLabel}</span>
      </div>
    </li>
  );
}

export default function FrequentDestinations({ listingId, ready }) {
  const [destinations, setDestinations] = useState(null);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  function load() {
    api
      .listingDestinations(listingId)
      .then(setDestinations)
      .catch((err) => setError(err.message));
  }

  useEffect(() => {
    if (!ready) return;
    setDestinations(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingId, ready]);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      setDestinations(await api.refreshListingDestinations(listingId));
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <>
      <div className="section-heading">
        <h3>Frequent destinations</h3>
        {ready && (
          <button
            className="icon-btn"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Recompute journeys"
            aria-label="Recompute journeys"
          >
            ↻
          </button>
        )}
      </div>

      {!ready ? (
        <p className="coming-soon">Waiting for listing details…</p>
      ) : error ? (
        <p className="error">Couldn't load frequent destinations: {error}</p>
      ) : destinations === null ? (
        <p>Loading…</p>
      ) : destinations.length === 0 ? (
        <p className="empty-state">
          No frequent destinations configured — add some from the Admin page.
        </p>
      ) : (
        <ul className="destination-list">
          {destinations.map((d) => (
            <DestinationRow key={d.destination_id} destination={d} />
          ))}
        </ul>
      )}
    </>
  );
}
