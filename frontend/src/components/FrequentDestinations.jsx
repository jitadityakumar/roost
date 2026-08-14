import { useEffect, useState } from "react";
import { api } from "../api.js";

function DestinationRow({ destination }) {
  if (!destination.resolved) {
    return (
      <li className="destination-row">
        <div className="destination-line1">
          <span className="destination-name">{destination.name}</span>
        </div>
        <div className="destination-unresolved">
          No train route found for {destination.day_label.slice(0, 3)} {destination.time} from any nearby
          station — will fall back to Google Maps once issue #25 lands.
        </div>
        {destination.planner_url && (
          <div className="destination-line3">
            <a href={destination.planner_url} target="_blank" rel="noreferrer">
              Search manually ↗
            </a>
          </div>
        )}
      </li>
    );
  }

  const routeLabel = [
    destination.kind === "direct" ? "direct" : `${destination.num_changes} change`,
    destination.operator,
    `via ${destination.origin_name} (${destination.origin_crs})`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="destination-row">
      <div className="destination-line1">
        <span className="destination-name">
          {destination.name} <span className="destination-station">· {destination.station_name}</span>
        </span>
        <span className="destination-duration good">{destination.duration_minutes} min</span>
      </div>
      <div className="destination-line2">
        <span className="destination-target">
          {destination.day_label.slice(0, 3)} {destination.time}
        </span>
        <span className="destination-route">{routeLabel}</span>
      </div>
      {destination.planner_url && (
        <div className="destination-line3">
          <a href={destination.planner_url} target="_blank" rel="noreferrer">
            View on Train Journey Planner ↗
          </a>
        </div>
      )}
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
