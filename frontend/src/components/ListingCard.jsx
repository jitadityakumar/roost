const STATUS_LABEL = {
  queued: "Fetching details…",
  running: "Fetching details…",
  failed: "Extraction failed",
  done: null,
};

export default function ListingCard({ listing, onSelect }) {
  const pending = listing.extraction_status !== "done";

  return (
    <div className={`listing-card ${pending ? "pending" : ""}`} onClick={() => onSelect(listing.id)}>
      {pending ? (
        <div className="stub-card">
          <span className={`spinner ${listing.extraction_status === "failed" ? "failed" : ""}`} />
          <div>
            <strong>{listing.url}</strong>
            <p>{STATUS_LABEL[listing.extraction_status] || listing.extraction_status}</p>
            {listing.extraction_status === "failed" && listing.extraction_error && (
              <p className="error">{listing.extraction_error}</p>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="listing-card-header">
            <span className="price">£{listing.price_gbp?.toLocaleString()}</span>
            <span className={`badge badge-${listing.user_status}`}>{listing.user_status}</span>
          </div>
          <p className="address">{listing.address}</p>
          <p className="meta">
            {listing.bedrooms ?? "?"} bed · {listing.bathrooms ?? "?"} bath · {listing.property_type || ""}
          </p>
        </>
      )}
    </div>
  );
}
