import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import FieldRow from "./FieldRow.jsx";

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
  { field: "broadband_top_speed", label: "Broadband top speed", editable: false },
];

export default function ListingDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [listing, setListing] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [media, setMedia] = useState(null);
  const [error, setError] = useState(null);

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

  async function handleStatusChange(newStatus) {
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

  return (
    <div className="listing-detail">
      <button className="back-btn" onClick={() => navigate(-1)}>
        ← Back
      </button>

      <div className="detail-header">
        <h2>{listing.address || listing.url}</h2>
        <div className="detail-actions">
          <select value={listing.user_status} onChange={(e) => handleStatusChange(e.target.value)}>
            <option value="active">Active</option>
            <option value="in_review">In-review</option>
          </select>
          <button onClick={handleRefresh}>Refresh</button>
          <button className="danger" onClick={handleDelete}>
            Delete
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
          <FieldRow key={f.field} listing={listing} onSave={handleFieldSave} {...f} />
        ))}
      </section>

      {listing.description && (
        <section>
          <h3>Description</h3>
          <p className="description">{listing.description}</p>
        </section>
      )}

      {media && (media.photos.length > 0 || media.floorplans.length > 0 || media.epc.length > 0) && (
        <section>
          <h3>Media</h3>
          {["photos", "floorplans", "epc"].map(
            (category) =>
              media[category].length > 0 && (
                <div key={category} className="media-category">
                  <h4>{category}</h4>
                  <div className="media-grid">
                    {media[category].map((filename) => (
                      <img key={filename} src={api.mediaUrl(id, category, filename)} alt={`${category} ${filename}`} />
                    ))}
                  </div>
                </div>
              )
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
