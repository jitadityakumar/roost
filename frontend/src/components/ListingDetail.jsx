import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DOMPurify from "dompurify";
import { api } from "../api.js";
import FieldRow from "./FieldRow.jsx";
import PhotoCarousel from "./PhotoCarousel.jsx";
import MediaGrid from "./MediaGrid.jsx";
import NearestStations from "./NearestStations.jsx";
import Commute from "./Commute.jsx";
import Mortgage from "./Mortgage.jsx";
import { PIPELINE_STATUS_LABEL } from "../pipelineStatus.js";

function formatBroadband(listing) {
  if (!listing.broadband_top_speed) return "—";
  const speed = String(listing.broadband_top_speed).replace(/mb\/?s?$/i, "").trim();
  const provider = listing.broadband_top_speed_provider;
  return `${speed} Mbps${provider ? ` · ${provider}` : ""}`;
}

function formatFetchedAt(listing) {
  if (!listing.rightmove_fetched_at) return "—";
  // Match listing_added_on's plain ISO-date display (FieldRow's default
  // rendering) -- date only, no time, no locale reformatting.
  return listing.rightmove_fetched_at.slice(0, 10);
}

// The jobs table shows current status, not a full audit log: every Refresh
// enqueues a fresh row per job_type rather than reusing the previous one
// (the jobs table is a history log by design), so a listing refreshed many
// times accumulates one group of rows per refresh. Collapse to just the
// most recent row per job_type -- the API already returns rows ordered by
// created_at ASC, so the last occurrence of each job_type is the latest.
function latestJobsByType(jobs) {
  const latest = new Map();
  for (const j of jobs) latest.set(j.job_type, j);
  return Array.from(latest.values());
}

const FIELDS = [
  { field: "price_gbp", label: "Price", editable: true, currency: true },
  { field: "address", label: "Address", editable: true },
  { field: "postcode", label: "Postcode", editable: true },
  { field: "property_type", label: "Type", editable: true },
  { field: "bedrooms", label: "Bedrooms", editable: true },
  { field: "bathrooms", label: "Bathrooms", editable: true },
  { field: "tenure", label: "Tenure", editable: true },
  { field: "lease_years_remaining", label: "Lease years remaining", sourceField: "lease_years_remaining_source", editable: true },
  { field: "service_charge_pa", label: "Service charge (per yr)", sourceField: "service_charge_source", editable: true, currency: true },
  { field: "service_charge_pm", label: "Service charge (per mo)", sourceField: "service_charge_source", editable: true, currency: true },
  { field: "council_tax_band", label: "Council tax band", sourceField: "council_tax_band_source", editable: true },
  { field: "floor_area_sqft", label: "Floor area", sourceField: "floor_area_sqft_source", editable: true, unit: "sq ft" },
  { field: "epc_current", label: "EPC current", sourceField: "epc_source", editable: true },
  { field: "epc_potential", label: "EPC potential", sourceField: "epc_source", editable: true },
  { field: "chain_free", label: "Chain free", sourceField: "chain_free_source", editable: true, boolean: true },
  { field: "cash_only", label: "Cash buyers only", sourceField: "cash_only_source", editable: true, boolean: true },
  { field: "garden", label: "Garden", sourceField: "garden_source", editable: true, boolean: true },
  { field: "parking", label: "Parking", sourceField: "parking_source", editable: true },
  { field: "agent_branch", label: "Agent", editable: false },
];

export default function ListingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [listing, setListing] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [media, setMedia] = useState(null);
  const [error, setError] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [l, j] = await Promise.all([api.get(id), api.jobs(id)]);
      setListing(l);
      setJobs(j);
      if (l.extraction_status === "done") {
        setMedia(await api.mediaList(id));
      }
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleFieldSave(field, value) {
    const updated = await api.patch(id, { fields: { [field]: value } });
    setListing(updated);
  }

  async function handleApprove() {
    const updated = await api.patch(id, { user_status: "approved" });
    setListing(updated);
  }

  function openReject() {
    setRejectReason("");
    setRejectError(null);
    setRejecting(true);
  }

  async function confirmReject() {
    if (!rejectReason.trim()) {
      setRejectError("A reason is required.");
      return;
    }
    const updated = await api.patch(id, { user_status: "rejected", rejection_reason: rejectReason.trim() });
    setListing(updated);
    setRejecting(false);
  }

  async function handleRefresh() {
    const updated = await api.refresh(id);
    setListing(updated);
    load();
  }

  async function handleDelete() {
    if (!confirm("Delete this listing and all its media? This cannot be undone.")) return;
    await api.remove(id);
    navigate("/");
  }

  if (error) return <p className="error">{error}</p>;
  if (!listing) return <p>Loading…</p>;

  const photoUrls = media ? media.photos.map((f) => api.mediaUrl(id, "photos", f)) : [];
  const floorplanUrls = media ? media.floorplans.map((f) => api.mediaUrl(id, "floorplans", f)) : [];
  const epcUrls = media ? media.epc.map((f) => api.mediaUrl(id, "epc", f)) : [];

  return (
    <div className="listing-detail">
      <button className="back-btn" onClick={() => navigate(`/${listing.user_status}`)}>
        ← Back
      </button>

      {photoUrls.length > 0 && <PhotoCarousel images={photoUrls} />}

      <div className="detail-header">
        <h2>{listing.address || listing.url}</h2>
        <div className="detail-actions">
          {listing.user_status !== "approved" && (
            <button className="status-toggle-btn" onClick={handleApprove}>
              Approve
            </button>
          )}
          {listing.user_status !== "rejected" && (
            <button className="status-toggle-btn warn" onClick={openReject}>
              Reject
            </button>
          )}
          <button className="icon-btn edit" onClick={() => setEditMode((v) => !v)} title="Edit" aria-label="Edit" aria-pressed={editMode}>
            ✎
          </button>
          <button className="icon-btn" onClick={handleRefresh} title="Refresh" aria-label="Refresh">
            ↻
          </button>
          <button className="icon-btn danger" onClick={handleDelete} title="Delete" aria-label="Delete">
            ✕
          </button>
        </div>
      </div>

      {rejecting && (
        <div className="reject-box">
          <label htmlFor="reject-reason">Reason for rejecting</label>
          <textarea
            id="reject-reason"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={3}
            autoFocus
          />
          {rejectError && <p className="error">{rejectError}</p>}
          <div className="reject-box-actions">
            <button className="status-toggle-btn warn" onClick={confirmReject}>
              Confirm reject
            </button>
            <button className="icon-btn" onClick={() => setRejecting(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {listing.user_status === "rejected" && listing.rejection_reason && (
        <p className="rejection-reason">Rejection reason: {listing.rejection_reason}</p>
      )}
      {listing.user_status !== "rejected" && listing.rejection_reason && (
        <p className="rejection-reason muted">Last rejection reason: {listing.rejection_reason}</p>
      )}

      <p>
        <a href={listing.url} target="_blank" rel="noreferrer">
          View on Rightmove ↗
        </a>
      </p>

      {listing.pipeline_status && (
        <p className={`pending-banner ${listing.pipeline_status === "failed" ? "failed" : ""}`}>
          {listing.pipeline_status === "failed"
            ? `Extraction failed${listing.extraction_error ? `: ${listing.extraction_error}` : ""}`
            : PIPELINE_STATUS_LABEL[listing.pipeline_status] || listing.pipeline_status}
        </p>
      )}

      <section className="fields">
        {FIELDS.map((f) => (
          <FieldRow key={f.field} listing={listing} onSave={handleFieldSave} editMode={editMode} {...f} />
        ))}
        <div className="field-row">
          <span className="field-label-col">
            <span className="field-label">Broadband top speed</span>
          </span>
          <span className="field-value">{formatBroadband(listing)}</span>
        </div>
        <FieldRow listing={listing} field="listing_added_on" label="Listed on" editable={false} onSave={handleFieldSave} editMode={editMode} />
        <div className="field-row">
          <span className="field-label-col">
            <span className="field-label">Fetched on</span>
          </span>
          <span className="field-value">{formatFetchedAt(listing)}</span>
        </div>
      </section>

      {listing.description && (
        <section>
          <h3>Description</h3>
          <div
            className="description"
            dangerouslySetInnerHTML={{
              __html: DOMPurify.sanitize(listing.description, {
                ALLOWED_TAGS: ["br", "p", "b", "strong", "i", "em", "ul", "ol", "li"],
                ALLOWED_ATTR: [],
              }),
            }}
          />
        </section>
      )}

      {Array.isArray(listing.key_features) && listing.key_features.length > 0 && (
        <section>
          <h3>Key features</h3>
          <ul className="key-features">
            {listing.key_features.map((feature, i) => (
              <li key={i}>{feature}</li>
            ))}
          </ul>
        </section>
      )}

      {Array.isArray(listing.nearest_stations_raw) && listing.nearest_stations_raw.length > 0 && (
        <section>
          <h3>Nearest stations</h3>
          <NearestStations stations={listing.nearest_stations_raw} />
        </section>
      )}

      {media && (floorplanUrls.length > 0 || epcUrls.length > 0) && (
        <section>
          <h3>Media</h3>
          {floorplanUrls.length > 0 && (
            <div className="media-category">
              <h4>floorplans</h4>
              <MediaGrid images={floorplanUrls} />
            </div>
          )}
          {epcUrls.length > 0 && (
            <div className="media-category">
              <h4>epc</h4>
              <MediaGrid images={epcUrls} />
            </div>
          )}
        </section>
      )}

      <section>
        <h3>Commute</h3>
        <Commute listingId={id} ready={listing.extraction_status === "done"} />
      </section>

      <section>
        <h3>Mortgage</h3>
        <Mortgage
          listingId={id}
          priceGbp={listing.price_gbp}
          ready={listing.extraction_status === "done"}
        />
      </section>

      <section>
        <h3>Jobs</h3>
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Lane</th>
              <th>Status</th>
              <th>Attempts</th>
              <th>Last error</th>
            </tr>
          </thead>
          <tbody>
            {latestJobsByType(jobs).map((j) => (
              <tr key={j.id}>
                <td>{j.job_type}</td>
                <td>{j.lane}</td>
                <td>{j.status}</td>
                <td>{j.attempts}</td>
                <td>{j.last_error || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
