import { Link } from "react-router-dom";
import { api } from "../api.js";
import { PIPELINE_STATUS_LABEL } from "../pipelineStatus.js";
import { useListingThumbnail } from "../hooks/useListingThumbnail.js";

export default function ListingCard({ listing, fromStatus }) {
  const pending = listing.extraction_status !== "done";
  const [thumbFilename, setThumbFilename] = useListingThumbnail(listing.id, { skip: pending });

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
              {/* Only shown once the pipeline is fully done -- a listing
                  still mid-processing may not have all its standards-relevant
                  fields yet, so a warning at that point would be premature. */}
              {!listing.pipeline_status && listing.has_warning && (
                <span className="warning-dot" title="Needs review" />
              )}
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
