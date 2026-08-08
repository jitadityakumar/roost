import { useEffect, useState } from "react";
import Lightbox from "./Lightbox.jsx";

export default function MediaGrid({ images }) {
  const [openIndex, setOpenIndex] = useState(null);

  useEffect(() => {
    setOpenIndex(null);
  }, [images]);

  if (images.length === 0) return null;

  return (
    <div className="media-grid">
      {images.map((src, i) => (
        <img key={src} src={src} alt="" onClick={() => setOpenIndex(i)} />
      ))}
      {openIndex !== null && (
        <Lightbox images={images} startIndex={openIndex} onClose={() => setOpenIndex(null)} />
      )}
    </div>
  );
}
