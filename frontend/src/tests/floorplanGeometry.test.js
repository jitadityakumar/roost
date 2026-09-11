import { describe, expect, it } from "vitest";
import {
  centroid,
  dist,
  parseLength,
  pointInPoly,
  polyArea,
  rectToPoints,
  shadeColor,
  sqftOf,
  ROOM_TYPES,
} from "../components/floorplanGeometry.js";

describe("polyArea", () => {
  it("computes area of a square", () => {
    const pts = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }];
    expect(polyArea(pts)).toBe(100);
  });

  it("is winding-order independent", () => {
    const cw = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }];
    const ccw = [...cw].reverse();
    expect(polyArea(ccw)).toBe(polyArea(cw));
  });

  it("handles an irregular polygon", () => {
    // L-shape: 10x10 minus a 5x5 notch = 75
    const pts = [
      { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 5 },
      { x: 5, y: 5 }, { x: 5, y: 10 }, { x: 0, y: 10 },
    ];
    expect(polyArea(pts)).toBe(75);
  });
});

describe("pointInPoly", () => {
  const square = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }];
  it("detects a point inside", () => {
    expect(pointInPoly({ x: 5, y: 5 }, square)).toBe(true);
  });
  it("detects a point outside", () => {
    expect(pointInPoly({ x: 15, y: 5 }, square)).toBe(false);
  });
});

describe("rectToPoints / centroid", () => {
  it("converts a rect to 4 corner points", () => {
    const pts = rectToPoints({ x0: 0, y0: 0, x1: 10, y1: 20 });
    expect(pts).toEqual([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 20 }, { x: 0, y: 20 }]);
  });
  it("computes centroid of a square", () => {
    expect(centroid(rectToPoints({ x0: 0, y0: 0, x1: 10, y1: 10 }))).toEqual({ x: 5, y: 5 });
  });
});

describe("dist", () => {
  it("computes euclidean distance", () => {
    expect(dist({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(5);
  });
});

describe("sqftOf", () => {
  it("divides pxArea by scale squared", () => {
    const shape = { pxArea: 1000, scalePxPerFt: 10 };
    expect(sqftOf(shape)).toBe(10);
  });

  it("returns null when scale is missing", () => {
    expect(sqftOf({ pxArea: 1000, scalePxPerFt: null })).toBeNull();
    expect(sqftOf({ pxArea: 1000, scalePxPerFt: 0 })).toBeNull();
    expect(sqftOf({ pxArea: 1000 })).toBeNull();
  });

  it("uses the shape's own snapshotted scale, not a hypothetical live one", () => {
    // Two shapes drawn at different calibrations must each use their own
    // scale -- this is the load-bearing "freeze scale at draw time" rule.
    const a = { pxArea: 1000, scalePxPerFt: 10 }; // 10 sqft
    const b = { pxArea: 1000, scalePxPerFt: 20 }; // 2.5 sqft
    expect(sqftOf(a)).toBe(10);
    expect(sqftOf(b)).toBe(2.5);
  });

  // Cross-check against the real current-flat trace
  // (~/claude/local-apps/house-tracker/floorplan-tool/project.json,
  // activeScale 22.75510473908948) -- confirms this port's formula
  // matches the standalone tool's own output on real data, not just
  // synthetic fixtures.
  it("matches the standalone tool's output on the real traced current-flat data", () => {
    const scale = 22.75510473908948;
    expect(sqftOf({ pxArea: 70499.56408748623, scalePxPerFt: scale })).toBeCloseTo(136.15348245934362, 6);
    expect(sqftOf({ pxArea: 121862.52002972533, scalePxPerFt: scale })).toBeCloseTo(235.34906489249798, 6);
    expect(sqftOf({ pxArea: 16342.783866517158, scalePxPerFt: scale })).toBeCloseTo(31.56227936027268, 6);
  });
});

describe("parseLength", () => {
  it.each([
    ["15'3\"", 15 + 3 / 12],
    ["15' 3\"", 15 + 3 / 12],
    ["15'", 15],
    ["15.25", 15.25],
    ["4.3m", 4.3 * 3.280839895],
    ["12ft", 12],
    ["12 ft", 12],
  ])("parses %s", (input, expected) => {
    expect(parseLength(input)).toBeCloseTo(expected, 6);
  });

  it("returns null for unparseable input", () => {
    expect(parseLength("banana")).toBeNull();
    expect(parseLength("")).toBeNull();
  });
});

describe("shadeColor", () => {
  it("returns the original color at index 0", () => {
    expect(shadeColor("#2e7d6b", 0)).toBe("#2e7d6b");
  });
  it("lightens progressively with increasing index", () => {
    const base = "#2e7d6b";
    const shade1 = shadeColor(base, 1);
    const shade2 = shadeColor(base, 2);
    expect(shade1).not.toBe(base);
    expect(shade2).not.toBe(shade1);
  });
  it("caps the lightening amount", () => {
    const shade10 = shadeColor("#2e7d6b", 10);
    const shade20 = shadeColor("#2e7d6b", 20);
    expect(shade10).toBe(shade20);
  });
});

describe("ROOM_TYPES", () => {
  it("has exactly the 5 fixed room type keys matching the backend", () => {
    expect(Object.keys(ROOM_TYPES).sort()).toEqual(
      ["bathroom", "bedroom", "hallway_storage", "outdoor", "reception_kitchen"].sort()
    );
  });
});
