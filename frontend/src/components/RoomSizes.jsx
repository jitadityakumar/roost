import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import RoomSizeComparison from "./RoomSizeComparison.jsx";

export default function RoomSizes({ listingId, ready, floorplanFilenames }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ready || !floorplanFilenames.length) return;
    let cancelled = false;
    setData(null);
    setError(null);
    api.floorplan
      .comparison(listingId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (cancelled) return;
        // A 404 here means "no listing trace with shapes yet" -- the
        // listing itself is already loaded by ListingDetail by the time
        // this fires, so a missing-listing 404 isn't a realistic
        // alternative reading. Matching on status (not the detail text)
        // keeps this from silently breaking if the backend's wording ever
        // changes -- see backend/app/routes/floorplan.py's
        // get_floorplan_comparison.
        if (err.status === 404) setData({ noTrace: true });
        else setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [listingId, ready, floorplanFilenames.length]);

  if (!ready || floorplanFilenames.length === 0) return null;

  function goToTrace() {
    navigate(`/listings/${listingId}/trace`);
  }

  return (
    <section>
      <h3>Room Sizes</h3>
      {error && <p className="error">Couldn't load room sizes: {error}</p>}
      {!error && data === null && <p>Loading…</p>}
      {!error && data?.noTrace && (
        <button className="status-toggle-btn" onClick={goToTrace}>
          Add trace
        </button>
      )}
      {!error && data && !data.noTrace && !data.baseline_has_shapes && (
        <p className="coming-soon">Trace a baseline floor plan in Admin to compare room sizes.</p>
      )}
      {!error && data && !data.noTrace && data.baseline_has_shapes && (
        <>
          <RoomSizeComparison data={data} />
          <button className="status-toggle-btn secondary" onClick={goToTrace} style={{ marginTop: "0.8rem" }}>
            Edit trace
          </button>
        </>
      )}
    </section>
  );
}
