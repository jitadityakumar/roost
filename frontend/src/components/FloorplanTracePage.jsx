import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import FloorplanTracer from "./FloorplanTracer.jsx";

// Dedicated route (issue #89 §7 decision 5) rather than an inline section
// or overlay -- ListingDetail is a scrolling read view and a 900px canvas
// doesn't belong in the middle of it; a routed page is also linkable and
// survives a refresh mid-trace.
export default function FloorplanTracePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [floorplans, setFloorplans] = useState(null);
  const [chosenImage, setChosenImage] = useState(null);
  const [trace, setTrace] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .mediaList(id)
      .then((m) => {
        setFloorplans(m.floorplans);
        if (m.floorplans.length === 1) setChosenImage(m.floorplans[0]);
      })
      .catch((err) => setError(err.message));
  }, [id]);

  useEffect(() => {
    if (!chosenImage) return;
    api.floorplan
      .getListingTrace(id, chosenImage)
      .then((t) => setTrace(t))
      .catch(() => setTrace({ rooms: [], shapes: [], active_scale: null }));
  }, [id, chosenImage]);

  async function handleSave(payload) {
    setSaving(true);
    setError(null);
    try {
      await api.floorplan.putListingTrace(id, {
        image_path: chosenImage,
        image_w: payload.imageW,
        image_h: payload.imageH,
        active_scale: payload.activeScale,
        rooms: payload.rooms,
        shapes: payload.shapes,
      });
      navigate(`/listings/${id}`);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (floorplans === null) return <p>Loading…</p>;
  if (floorplans.length === 0) {
    return (
      <div className="listing-detail">
        <button className="back-btn" onClick={() => navigate(`/listings/${id}`)}>← Back to listing</button>
        <p className="error">This listing has no floor plan image to trace.</p>
      </div>
    );
  }

  if (!chosenImage) {
    return (
      <div className="listing-detail">
        <button className="back-btn" onClick={() => navigate(`/listings/${id}`)}>← Back to listing</button>
        <h2>Which floor plan image?</h2>
        <p className="hint">This listing has more than one floor plan image -- a trace is tied to one specific image.</p>
        <div className="media-grid">
          {floorplans.map((f) => (
            <img
              key={f}
              src={api.mediaUrl(id, "floorplans", f)}
              alt={f}
              onClick={() => setChosenImage(f)}
            />
          ))}
        </div>
      </div>
    );
  }

  if (!trace) return <p>Loading…</p>;

  return (
    <div className="listing-detail tracer-page">
      <button className="back-btn" onClick={() => navigate(`/listings/${id}`)}>← Back to listing</button>
      <h2>Trace room sizes</h2>
      <FloorplanTracer
        imageSrc={api.mediaUrl(id, "floorplans", chosenImage)}
        initialRooms={trace.rooms}
        initialShapes={trace.shapes}
        initialScale={trace.active_scale}
        onSave={handleSave}
        saving={saving}
      />
    </div>
  );
}
