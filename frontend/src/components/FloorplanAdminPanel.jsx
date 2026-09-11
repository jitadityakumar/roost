import { useEffect, useState } from "react";
import { api } from "../api.js";
import FloorplanTracer from "./FloorplanTracer.jsx";
import { sqftOf } from "./floorplanGeometry.js";

// Admin panel hosting the baseline trace -- the current-residence floor
// plan every listing's Room Sizes comparison is measured against. Per
// issue #89 §3b: kept lazily inert (no fetch/decode of the baseline image)
// until this panel is actually selected, since AdminPage mounts all panels
// simultaneously and a canvas decoding a large embedded image on every
// Admin page load regardless of which panel is visible would be wasteful.
export default function FloorplanAdminPanel({ active }) {
  const [loaded, setLoaded] = useState(false);
  const [baseline, setBaseline] = useState(null);
  const [imageSrc, setImageSrc] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [tracerKey, setTracerKey] = useState(0);

  useEffect(() => {
    if (!active || loaded) return;
    api.floorplan
      .getBaseline()
      .then((b) => {
        setBaseline(b);
        setImageSrc(b.image_blob || null);
        setLoaded(true);
      })
      .catch((err) => setError(err.message));
  }, [active, loaded]);

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

  if (!active) return null;
  if (error) return <p className="error">{error}</p>;
  if (!loaded) return <p>Loading…</p>;

  const totalSqft = baseline.shapes.reduce((a, s) => a + (sqftOf(s) || 0), 0);

  return (
    <div>
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
        {baseline.shapes.length > 0 && (
          <span className="floorplan-admin-scale-readout">
            Current baseline total: <b>{totalSqft.toFixed(1)} sq ft</b> ({baseline.shapes.length} shape{baseline.shapes.length === 1 ? "" : "s"})
          </span>
        )}
      </div>

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
