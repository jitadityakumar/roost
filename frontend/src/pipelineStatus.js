// pipeline_status is derived server-side from the jobs table (see
// backend/app/jobs/pipeline_status.py) and covers the whole pipeline, not
// just the initial Rightmove fetch: queued -> fetching (rightmove + media)
// -> processing (llm lane) -> failed, or absent once everything's done.
// Shared between ListingCard and ListingDetail so the two badges can't
// silently drift out of sync.
export const PIPELINE_STATUS_LABEL = {
  queued: "Queued",
  fetching: "Fetching details…",
  processing: "Processing…",
  failed: "Extraction failed",
};
