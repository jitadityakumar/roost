import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DOMPurify from "dompurify";
import { api } from "../api.js";
import FieldRow from "./FieldRow.jsx";
import PhotoCarousel from "./PhotoCarousel.jsx";
import MediaGrid from "./MediaGrid.jsx";

function formatBroadband(listing) {
  if (!listing.broadband_top_speed) return "—";
  const speed = String(listing.broadband_top_speed).replace(/mb\/?s?$/i, "").trim();
  const provider = listing.broadband_top_speed_provider;
  return `${speed} Mbps${provider ? ` · ${provider}` : ""}`;
}

const FIELDS = [
  { field: "price_gbp", label: "Price (£)", editable: true },
  { field: "address", label: "Address", editable: true },
  { field: "postcode", label: "Postcode", editable: true },
  { field: "property_type", label: "Type", editable: true },
  { field: "bedrooms", label: "Bedrooms", editable: true },
  { field: "bathrooms", label: "Bathrooms", editable: true },
  { field: "tenure", label: "Tenure", editable: true },
  { field: "lease_years_remaining", label: "Lease years remaining", sourceField: "lease_years_remaining_source", editable: true },
  { field: "service_charge_pa", label: "Service charge (£/yr)", sourceField: "service_charge_source", editable: true },
  { field: "service_charge_pm", label: "Service charge (£/mo)", sourceField: "service_charge_source", editable: true },
  { field: "council_tax_band", label: "Council tax band", sourceField: "council_tax_band_source", editable: true },
  { field: "floor_area_sqft", label: "Floor area (sqft)", sourceField: "floor_area_sqft_source", editable: true },
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

  async function handleStatusToggle() {
    const newStatus = listing.user_status === "active" ? "in_review" : "active";
    const updated = await api.patch(id, { user_status: newStatus });
    setListing(updated);
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
      <button
        className="back-btn"
        onClick={() => navigate(listing.user_status === "active" ? "/active" : "/in-review")}
      >
        ← Back
      </button>

      {photoUrls.length > 0 && <PhotoCarousel images={photoUrls} />}

      <div className="detail-header">
        <h2>{listing.address || listing.url}</h2>
        <div className="detail-actions">
          <button className="status-toggle-btn" onClick={handleStatusToggle}>
            {listing.user_status === "active" ? "Move → In review" : "Move → Active"}
          </button>
          <button className="icon-btn" onClick={() => setEditMode((v) => !v)} title="Edit" aria-label="Edit" aria-pressed={editMode}>
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

      <p>
        <a href={listing.url} target="_blank" rel="noreferrer">
          View on Rightmove ↗
        </a>
      </p>

      {listing.extraction_status !== "done" && (
        <p className="pending-banner">
          {listing.extraction_status === "failed"
            ? `Extraction failed: ${listing.extraction_error || "unknown error"}`
            : "Fetching details…"}
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

      <section className="stub-section">
        <h3>Commute</h3>
        <p className="coming-soon">Coming soon — commute-time joins land in Phase 2.</p>
      </section>

      <section className="stub-section">
        <h3>Mortgage</h3>
        <p className="coming-soon">Coming soon — mortgage affordability joins land in Phase 2.</p>
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
            {jobs.map((j) => (
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
