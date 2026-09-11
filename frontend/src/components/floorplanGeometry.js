// Pure geometry/maths helpers for the floor plan tracer, ported from the
// standalone ~/claude/local-apps/house-tracker/floorplan-tool/index.html.
// No DOM/canvas dependency here so this stays unit-testable -- the canvas
// component (FloorplanTracer.jsx) is the only thing that touches a <canvas>.

// Fixed room types -- these are the only ones a user traces by hand.
// Hallway/Storage isn't a button here: it's computed as the remainder of a
// known internal sq ft figure minus these traced non-outdoor rooms (see
// backend/app/floorplan/compare.py's HALLWAY_STORAGE handling). Keys must
// match the backend's compare.py ROOM_TYPES exactly.
export const ROOM_TYPES = {
  bedroom: { label: "Bedroom", color: "#2e7d6b" },
  reception_kitchen: { label: "Reception/Kitchen", color: "#2f5f83" },
  bathroom: { label: "Bathroom", color: "#0f7a8a" },
  outdoor: { label: "Outdoor Space", color: "#a8631c" },
};

// Fixed swatch palette offered in the room color picker, plus a custom
// native color input for anything outside this set.
export const COLOR_PALETTE = [
  "#2e7d6b", "#2f5f83", "#0f7a8a", "#3d8f4a", "#5a5fb0",
  "#a8631c", "#a83f30", "#c2185b", "#6a4c93", "#8a6d1f",
];

// Lightens a hex color progressively (mix toward white) for each additional
// instance of a room type, so same-type rooms read as a family on canvas.
export function shadeColor(hex, index) {
  const amount = Math.min(index * 0.16, 0.7);
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  const mix = (c) => Math.round(c + (255 - c) * amount);
  return "#" + [mix(r), mix(g), mix(b)].map((v) => v.toString(16).padStart(2, "0")).join("");
}

// Shoelace formula -- signed area, absolute value taken so winding order
// doesn't matter.
export function polyArea(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

export function pointInPoly(pt, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i].x, yi = pts[i].y, xj = pts[j].x, yj = pts[j].y;
    const hit = (yi > pt.y) !== (yj > pt.y) && pt.x < ((xj - xi) * (pt.y - yi)) / (yj - yi || 1e-9) + xi;
    if (hit) inside = !inside;
  }
  return inside;
}

export function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function rectToPoints(r) {
  return [{ x: r.x0, y: r.y0 }, { x: r.x1, y: r.y0 }, { x: r.x1, y: r.y1 }, { x: r.x0, y: r.y1 }];
}

export function centroid(pts) {
  let x = 0, y = 0;
  for (const p of pts) { x += p.x; y += p.y; }
  return { x: x / pts.length, y: y / pts.length };
}

// Sq ft is never stored -- computed from a shape's own pxArea and the
// scale that was active *when that shape was drawn* (shape.scalePxPerFt),
// not any "live" scale on the trace. That's deliberate: recalibrating
// mid-trace must not retroactively resize already-drawn shapes. A shape
// with no scale yet (scalePxPerFt falsy) has no area at all.
export function sqftOf(shape) {
  if (!shape.scalePxPerFt) return null;
  return shape.pxArea / (shape.scalePxPerFt * shape.scalePxPerFt);
}

// Parses a real-world length typed during calibration: feet+inches
// (15'3", 15' 3", 15'), meters (4.3m), or plain feet (15 / 15ft).
// Returns feet as a float, or null if unparseable.
export function parseLength(str) {
  str = str.trim();
  let m = str.match(/^(\d+(?:\.\d+)?)\s*'\s*(\d+(?:\.\d+)?)?\s*"?$/);
  if (m) return parseFloat(m[1]) + (m[2] ? parseFloat(m[2]) : 0) / 12;
  m = str.match(/^(\d+(?:\.\d+)?)\s*m$/i);
  if (m) return parseFloat(m[1]) * 3.280839895;
  m = str.match(/^(\d+(?:\.\d+)?)\s*(ft)?$/i);
  if (m) return parseFloat(m[1]);
  return null;
}
