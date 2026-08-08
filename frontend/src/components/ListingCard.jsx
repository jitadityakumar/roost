import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

const STATUS_LABEL = {
  queued: "Fetching details…",
  running: "Fetching details…",
  failed: "Extraction failed",
  done: null,
};

const USER_STATUS_LABEL = {
  active: "Active",
  in_review: "In-review",
};

// Extraction flips to "done" before the media_download job (which writes
// photos/01.jpeg) has necessarily finished, so the very first thumbnail
// request can 404 in the normal case, not just as an edge case. Retry with
// backoff for a few seconds before giving up on the thumbnail.
const THUMB_MAX_RETRIES = 8;
const THUMB_RETRY_DELAY_MS = 2000;

export default function ListingCard({ listing }) {
  const pending = listing.extraction_status !== "done";
  const [thumbAttempt, setThumbAttempt] = useState(0);
  const [thumbFailed, setThumbFailed] = useState(false);

  useEffect(() => {
    setThumbAttempt(0);
    setThumbFailed(false);
  }, [listing.id]);

  const handleThumbError = () => {
    if (thumbAttempt >= THUMB_MAX_RETRIES) {
      setThumbFailed(true);
    } else {
      setTimeout(() => setThumbAttempt((n) => n + 1), THUMB_RETRY_DELAY_MS);
    }
  };

  return (
    <Link className={`listing-card ${pending ? "pending" : ""}`} to={`/listings/${listing.id}`}>
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
          {!thumbFailed && (
            <img
              className="listing-card-thumb"
              src={`${api.mediaUrl(listing.id, "photos", "01.jpeg")}${thumbAttempt ? `?retry=${thumbAttempt}` : ""}`}
              alt={listing.address ? `Photo of ${listing.address}` : "Listing photo"}
              loading="lazy"
              onError={handleThumbError}
            />
          )}
          <div className="listing-card-body">
            <div className="listing-card-header">
              <span className="price">£{listing.price_gbp?.toLocaleString()}</span>
              <span className={`badge badge-${listing.user_status}`}>
                {USER_STATUS_LABEL[listing.user_status] || listing.user_status}
              </span>
            </div>
            <p className="address">{listing.address}</p>
            <p className="meta">
              {listing.bedrooms ?? "?"} bed · {listing.bathrooms ?? "?"} bath · {listing.property_type || ""}
            </p>
          </div>
        </>
      )}
    </Link>
  );
}
