import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { sqftOf } from "./floorplanGeometry.js";

// Summary panel only -- the actual tracing happens on the dedicated
// /admin/floorplan-baseline/trace route (FloorplanBaselineTracePage), since
// embedding FloorplanTracer's canvas inside AdminPage's sidebar-shell
// layout left it squeezed into a fraction of the browser width. Per issue
// #89 §3b: kept lazily inert until this panel is actually selected, since
// AdminPage mounts all panels simultaneously.
export default function FloorplanAdminPanel({ active }) {
  const [loaded, setLoaded] = useState(false);
  const [baseline, setBaseline] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!active || loaded) return;
    api.floorplan
      .getBaseline()
      .then((b) => {
        setBaseline(b);
        setLoaded(true);
      })
      .catch((err) => setError(err.message));
  }, [active, loaded]);

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
        comparison automatically. Tracing opens in a dedicated full-width page.
      </p>

      {baseline.image_blob ? (
        <p className="floorplan-admin-scale-readout">
          Current baseline total: <b>{totalSqft.toFixed(1)} sq ft</b> ({baseline.shapes.length} shape{baseline.shapes.length === 1 ? "" : "s"})
          {baseline.internal_sqft != null && <> · internal sq ft: <b>{baseline.internal_sqft}</b></>}
        </p>
      ) : (
        <p className="empty-state">No baseline image set yet.</p>
      )}

      <Link
        to="/admin/floorplan-baseline/trace"
        className="ghost"
        style={{ display: "inline-block", cursor: "pointer", padding: "0.4rem 0.8rem", border: "1px solid var(--border)", borderRadius: "6px" }}
      >
        {baseline.image_blob ? "Edit baseline trace…" : "Set baseline image…"}
      </Link>
    </div>
  );
}
