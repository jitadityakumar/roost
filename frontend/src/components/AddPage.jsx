import { useState } from "react";
import { Link } from "react-router-dom";
import AddListingForm from "./AddListingForm.jsx";

export default function AddPage() {
  const [added, setAdded] = useState([]);

  function handleAdded(listing) {
    setAdded((prev) => [listing, ...prev]);
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
          {added.map((listing, index) => (
            <li key={`${listing.id}-${index}`}>
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
