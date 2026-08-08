import { useState } from "react";
import { api } from "../api.js";

export default function AddListingForm({ onAdded }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.create(url.trim());
      setUrl("");
      onAdded(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="add-listing-form" onSubmit={handleSubmit}>
      <input
        type="url"
        placeholder="Paste a Rightmove property URL…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        required
      />
      <button type="submit" disabled={submitting}>
        {submitting ? "Adding…" : "Add"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
