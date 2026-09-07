import { useEffect, useState } from "react";
import { api } from "../api.js";

// Extraction flips to "done" before the media_download job (which writes
// the photo files) has necessarily finished, so the photo list can come
// back empty on the first request in the normal case, not just as an edge
// case. Retry with backoff before giving up on the thumbnail. The filename
// (and extension) also isn't fixed — it's whatever Rightmove served for
// that image — so the actual first filename has to come from the media
// list rather than being assumed as "01.jpeg".
const THUMB_MAX_RETRIES = 8;
const THUMB_RETRY_DELAY_MS = 2000;

// Shared by ListingCard (list view) and MapPage (popup on the shortlist
// map, issue #86) — both show the same primary-photo thumbnail.
export function useListingThumbnail(listingId, { skip = false } = {}) {
  const [thumbFilename, setThumbFilename] = useState(null);

  useEffect(() => {
    if (skip) return;
    let cancelled = false;

    const tryLoad = async (attempt) => {
      let media;
      try {
        media = await api.mediaList(listingId);
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
  }, [listingId, skip]);

  return [thumbFilename, setThumbFilename];
}
