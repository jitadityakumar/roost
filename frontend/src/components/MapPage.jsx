import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { api } from "../api.js";
import { PIPELINE_STATUS_LABEL } from "../pipelineStatus.js";
import { USER_STATUSES, USER_STATUS_LABEL, STATUS_COLOR_VAR } from "../userStatus.js";
import { useListingThumbnail } from "../hooks/useListingThumbnail.js";

// London-wide fallback view for when there are no plottable listings yet
// (or none pass the current filter) -- FitBounds below overrides this the
// moment there's at least one pin to frame.
const DEFAULT_CENTER = [51.5074, -0.1278];
const DEFAULT_ZOOM = 10;

function getStatusColor(status) {
  const { cssVar, fallback } = STATUS_COLOR_VAR[status] || {};
  if (typeof window === "undefined" || !cssVar) return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
  return value || fallback;
}

// Re-frames the map to fit every currently-visible pin whenever the filtered
// set changes -- a plain fixed center/zoom would leave most pins off-screen
// once a status filter narrows the set to a handful of scattered listings.
function FitBounds({ listings }) {
  const map = useMap();
  const key = listings.map((l) => `${l.id}:${l.latitude}:${l.longitude}`).join("|");

  useEffect(() => {
    if (listings.length === 0) return;
    const bounds = listings.map((l) => [l.latitude, l.longitude]);
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return null;
}

function MapPopupCard({ listing }) {
  const pending = listing.extraction_status !== "done";
  const [thumbFilename] = useListingThumbnail(listing.id, { skip: pending });

  return (
    <div className="map-popup">
      <div className="map-popup-thumb">
        {thumbFilename ? (
          <img
            src={api.mediaUrl(listing.id, "photos", thumbFilename)}
            alt={listing.address ? `Photo of ${listing.address}` : "Listing photo"}
            loading="lazy"
          />
        ) : (
          <span className="map-popup-thumb-placeholder" />
        )}
        {listing.pipeline_status && (
          <span className={`badge badge-pipeline-${listing.pipeline_status}`}>
            {PIPELINE_STATUS_LABEL[listing.pipeline_status] || listing.pipeline_status}
          </span>
        )}
      </div>
      <div className="map-popup-body">
        <span className={`status-dot ${listing.user_status}`} />
        <span className="price">£{listing.price_gbp?.toLocaleString()}</span>
        <p className="address">{listing.address}</p>
        <p className="meta">
          {listing.bedrooms ?? "?"} bed · {listing.bathrooms ?? "?"} bath · {listing.property_type || ""}
        </p>
        <Link to={`/listings/${listing.id}`}>View listing →</Link>
      </div>
    </div>
  );
}

export default function MapPage() {
  const [listings, setListings] = useState([]);
  const [error, setError] = useState(null);
  // Multi-select: any combination of statuses can be toggled on/off,
  // defaulting to Triage only (issue #86).
  const [selectedStatuses, setSelectedStatuses] = useState(() => new Set(["triage"]));

  const load = useCallback(async () => {
    try {
      const data = await api.list();
      setListings(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const plottable = useMemo(
    () => listings.filter((l) => typeof l.latitude === "number" && typeof l.longitude === "number"),
    [listings]
  );
  const visible = useMemo(
    () => plottable.filter((l) => selectedStatuses.has(l.user_status)),
    [plottable, selectedStatuses]
  );

  const toggleStatus = (status) => {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const allSelected = selectedStatuses.size === USER_STATUSES.length;
  const toggleAll = () => {
    setSelectedStatuses(allSelected ? new Set() : new Set(USER_STATUSES));
  };

  return (
    <div className="dashboard map-page">
      <Link className="back-btn" to="/">
        ← Back to Home
      </Link>
      <h2>Map view</h2>

      {error && <p className="error">{error}</p>}

      <div className="map-toolbar">
        <div className="filters">
          {USER_STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              className={`filter-btn ${selectedStatuses.has(status) ? "active" : ""}`}
              aria-pressed={selectedStatuses.has(status)}
              onClick={() => toggleStatus(status)}
            >
              <span className="dot" style={{ background: getStatusColor(status) }} />
              {USER_STATUS_LABEL[status]}
            </button>
          ))}
          <button type="button" className="filter-btn" onClick={toggleAll}>
            {allSelected ? "clear all" : "select all"}
          </button>
        </div>
        <span className="filter-count">
          {visible.length} of {plottable.length} listings shown
        </span>
      </div>

      <MapContainer center={DEFAULT_CENTER} zoom={DEFAULT_ZOOM} scrollWheelZoom={false} className="map-container">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds listings={visible} />
        {visible.map((l) => (
          <CircleMarker
            key={l.id}
            center={[l.latitude, l.longitude]}
            radius={8}
            pathOptions={{
              color: getStatusColor(l.user_status),
              fillColor: getStatusColor(l.user_status),
              fillOpacity: 0.55,
              weight: 2,
            }}
          >
            <Popup>
              <MapPopupCard listing={l} />
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
