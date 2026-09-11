import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import FloorplanTracer from "./FloorplanTracer.jsx";

// Dedicated route for the baseline trace, same rationale as
// FloorplanTracePage (issue #89 follow-up): embedding FloorplanTracer
// inside AdminPage's sidebar-shell layout left the canvas squeezed into a
// fraction of the browser width. This is web-only, deliberately not
// mobile-optimized -- tracing is expected to happen at a computer.
export default function FloorplanBaselineTracePage() {
  const navigate = useNavigate();
  const [baseline, setBaseline] = useState(null);
  const [imageSrc, setImageSrc] = useState(null);
  const [internalSqft, setInternalSqft] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [tracerKey, setTracerKey] = useState(0);

  useEffect(() => {
    api.floorplan
      .getBaseline()
      .then((b) => {
        setBaseline(b);
        setImageSrc(b.image_blob || null);
        setInternalSqft(b.internal_sqft != null ? String(b.internal_sqft) : "");
      })
      .catch((err) => setError(err.message));
  }, []);

  function handleImageFile(file) {
    if (!file) return;
    if (baseline && baseline.shapes.length && !confirm("Loading a new image clears all current shapes. Continue?")) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      setBaseline((prev) => ({ ...prev, rooms: [], shapes: [], active_scale: null }));
      setImageSrc(e.target.result);
      setTracerKey((k) => k + 1); // remount FloorplanTracer with fresh initial state
    };
    reader.readAsDataURL(file);
  }

  async function handleSave(payload) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.floorplan.putBaseline({
        image_blob: imageSrc,
        image_w: payload.imageW,
        image_h: payload.imageH,
        active_scale: payload.activeScale,
        internal_sqft: internalSqft.trim() === "" ? null : parseFloat(internalSqft),
        rooms: payload.rooms,
        shapes: payload.shapes,
      });
      setBaseline(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!baseline) return <p>Loading…</p>;

  return (
    <div className="tracer-page">
      <button className="back-btn" onClick={() => navigate("/admin")}>← Back to admin</button>
      <h2>Floor plan baseline</h2>
      <p className="hint">
        Trace your current residence's floor plan here -- every listing's Room Sizes section
        compares against this baseline. Editable any time; re-tracing updates every existing
        comparison automatically.
      </p>

      <div className="floorplan-admin-image-row">
        <label className="ghost" style={{ cursor: "pointer", padding: "0.4rem 0.8rem", border: "1px solid var(--border)", borderRadius: "6px" }}>
          {imageSrc ? "Change baseline image…" : "Set baseline image…"}
          <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => handleImageFile(e.target.files[0])} />
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
          Internal sq ft (whole property):
          <input
            type="number"
            min="0"
            step="1"
            value={internalSqft}
            onChange={(e) => setInternalSqft(e.target.value)}
            placeholder="e.g. 850"
            style={{ width: "7rem" }}
          />
        </label>
      </div>
      <p className="hint">
        Used to work out Hallway/Storage automatically -- it's the remainder after subtracting
        the traced Bedroom/Reception-Kitchen/Bathroom rooms below, so it doesn't need tracing
        itself. Saved along with the trace when you hit Save.
      </p>

      {imageSrc ? (
        <FloorplanTracer
          key={tracerKey}
          imageSrc={imageSrc}
          initialRooms={baseline.rooms}
          initialShapes={baseline.shapes}
          initialScale={baseline.active_scale}
          onSave={handleSave}
          saving={saving}
        />
      ) : (
        <p className="empty-state">Set a baseline image to start tracing.</p>
      )}
    </div>
  );
}
