import { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import ListingCard from "./ListingCard.jsx";

const TITLES = {
  active: "Active",
  in_review: "In-review",
};

export default function ListingsPage({ status }) {
  const [listings, setListings] = useState([]);
  const [sortBy, setSortBy] = useState("newest");
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api.list(status);
      setListings(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is still extracting, so stub cards upgrade in place.
  useEffect(() => {
    const hasPending = listings.some((l) => l.extraction_status === "queued" || l.extraction_status === "running");
    if (!hasPending) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [listings, load]);

  const sorted = [...listings].sort((a, b) => {
    if (sortBy === "price_asc") return (a.price_gbp || Infinity) - (b.price_gbp || Infinity);
    if (sortBy === "price_desc") return (b.price_gbp || -Infinity) - (a.price_gbp || -Infinity);
    return new Date(b.created_at) - new Date(a.created_at);
  });

  return (
    <div className="dashboard">
      <h2>{TITLES[status] || status}</h2>

      <div className="controls">
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="newest">Newest first</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
        </select>
      </div>

      {error && <p className="error">{error}</p>}

      {sorted.length === 0 ? (
        <p className="empty-state">
          {status === "in_review"
            ? "Nothing in review — add a property to get started."
            : "No active listings yet — promote one from in-review."}
        </p>
      ) : (
        <div className="listing-grid">
          {sorted.map((l) => (
            <ListingCard key={l.id} listing={l} />
          ))}
        </div>
      )}
    </div>
  );
}
