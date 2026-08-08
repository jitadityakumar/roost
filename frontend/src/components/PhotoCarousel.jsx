import { useEffect, useRef, useState } from "react";
import Lightbox from "./Lightbox.jsx";
import { isTypingTarget } from "./domUtils.js";

export default function PhotoCarousel({ images }) {
  const [index, setIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const touchStartX = useRef(null);

  const prev = () => setIndex((i) => (i - 1 + images.length) % images.length);
  const next = () => setIndex((i) => (i + 1) % images.length);

  useEffect(() => {
    setIndex(0);
  }, [images]);

  useEffect(() => {
    function onKey(e) {
      if (lightboxOpen) return;
      if (isTypingTarget(e.target)) return;
      if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [images.length, lightboxOpen]);

  function onTouchStart(e) {
    touchStartX.current = e.touches[0].clientX;
  }

  function onTouchEnd(e) {
    if (touchStartX.current === null) return;
    const delta = e.changedTouches[0].clientX - touchStartX.current;
    if (delta > 40) prev();
    else if (delta < -40) next();
    touchStartX.current = null;
  }

  if (images.length === 0) return null;

  return (
    <div className="photo-carousel">
      <div className="photo-carousel-main" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
        <img
          src={images[index]}
          alt={`Photo ${index + 1}`}
          onClick={() => setLightboxOpen(true)}
        />
        {images.length > 1 && (
          <>
            <button className="carousel-nav carousel-prev" onClick={prev} aria-label="Previous photo">
              ‹
            </button>
            <button className="carousel-nav carousel-next" onClick={next} aria-label="Next photo">
              ›
            </button>
            <div className="carousel-counter">
              {index + 1} / {images.length}
            </div>
          </>
        )}
      </div>

      {lightboxOpen && (
        <Lightbox images={images} startIndex={index} onClose={() => setLightboxOpen(false)} />
      )}
    </div>
  );
}
