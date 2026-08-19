import { useState } from "react";
import { Link } from "react-router-dom";
import AddListingForm from "./AddListingForm.jsx";

let nextKey = 0;

export default function AddPage() {
  const [added, setAdded] = useState([]);

  function handleAdded(listing) {
    // Same listing can legitimately be submitted (and land in this list)
    // more than once in a session -- a stable per-submission key keeps
    // React from remounting the whole list on every add, unlike keying off
    // listing.id (collides on resubmit) or array index (shifts on prepend).
    setAdded((prev) => [{ ...listing, _key: nextKey++ }, ...prev]);
  }

  return (
    <div className="add-page">
      <h2>Add a property</h2>
      <p className="hint">
        Paste a Rightmove property URL. It's added straight away as
        in-review — review the extracted data on its own page and promote it
        to active once you're happy with it.
      </p>
      <AddListingForm onAdded={handleAdded} />

      {added.length > 0 && (
        <ul className="added-list">
          {added.map((listing) => (
            <li key={listing._key}>
              {listing.already_tracked ? (
                <>
                  Note — <Link to={`/listings/${listing.id}`}>{listing.url}</Link>
                  <br />
                  This listing has already been added.
                </>
              ) : (
                <>
                  Added — <Link to={`/listings/${listing.id}`}>{listing.url}</Link>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
