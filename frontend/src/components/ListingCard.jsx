import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { PIPELINE_STATUS_LABEL } from "../pipelineStatus.js";
import { USER_STATUS_LABEL } from "../userStatus.js";

// Extraction flips to "done" before the media_download job (which writes
// the photo files) has necessarily finished, so the photo list can come
// back empty on the first request in the normal case, not just as an edge
// case. Retry with backoff before giving up on the thumbnail. The filename
// (and extension) also isn't fixed — it's whatever Rightmove served for
// that image — so the actual first filename has to come from the media
// list rather than being assumed as "01.jpeg".
const THUMB_MAX_RETRIES = 8;
const THUMB_RETRY_DELAY_MS = 2000;

export default function ListingCard({ listing, fromStatus }) {
  const pending = listing.extraction_status !== "done";
  const [thumbFilename, setThumbFilename] = useState(null);

  useEffect(() => {
    if (pending) return;
    let cancelled = false;

    const tryLoad = async (attempt) => {
      let media;
      try {
        media = await api.mediaList(listing.id);
      } catch {
        if (!cancelled) setThumbFilename("");
        return;
      }
      if (cancelled) return;
      const first = (media.photos || [])[0];
      if (first) {
        setThumbFilename(first);
      } else if (attempt < THUMB_MAX_RETRIES) {
        setTimeout(() => tryLoad(attempt + 1), THUMB_RETRY_DELAY_MS);
      } else {
        setThumbFilename("");
      }
    };
    tryLoad(0);

    return () => {
      cancelled = true;
    };
  }, [listing.id, pending]);

  return (
    <Link
      className={`listing-card ${pending ? "pending" : ""}`}
      to={`/listings/${listing.id}`}
      state={{ from: fromStatus }}
    >
      {pending ? (
        <div className="stub-card">
          <span className={`spinner ${listing.pipeline_status === "failed" ? "failed" : ""}`} />
          <div>
            <strong>{listing.url}</strong>
            <p>{PIPELINE_STATUS_LABEL[listing.pipeline_status] || "Queued"}</p>
            {listing.pipeline_status === "failed" && listing.extraction_error && (
              <p className="error">{listing.extraction_error}</p>
            )}
          </div>
        </div>
      ) : (
        <>
          {thumbFilename && (
            <img
              className="listing-card-thumb"
              src={api.mediaUrl(listing.id, "photos", thumbFilename)}
              alt={listing.address ? `Photo of ${listing.address}` : "Listing photo"}
              loading="lazy"
              onError={() => setThumbFilename("")}
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
            {listing.pipeline_status && (
              <span className={`badge badge-pipeline-${listing.pipeline_status}`}>
                {PIPELINE_STATUS_LABEL[listing.pipeline_status] || listing.pipeline_status}
              </span>
            )}
          </div>
        </>
      )}
    </Link>
  );
}
