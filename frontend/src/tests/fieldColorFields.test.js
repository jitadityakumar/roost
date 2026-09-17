import { describe, expect, it } from "vitest";
import { numericColorFor } from "../fieldColorFields.js";

describe("numericColorFor", () => {
  it("returns null with no rule or no value", () => {
    expect(numericColorFor(5, null)).toBeNull();
    expect(numericColorFor(null, { green_cutoff: "1", red_cutoff: "2", higher_is_better: true })).toBeNull();
  });

  it("colours red when past the red cutoff, lower_is_better", () => {
    const rule = { green_cutoff: "1.0", red_cutoff: "2.0", higher_is_better: false };
    expect(numericColorFor(2.5, rule)).toBe("red");
  });

  it("colours green when past the green cutoff, higher_is_better", () => {
    const rule = { green_cutoff: "10", red_cutoff: "2", higher_is_better: true };
    expect(numericColorFor(15, rule)).toBe("green");
  });

  it("treats cutoffs as inclusive at both ends", () => {
    const rule = { green_cutoff: "10", red_cutoff: "2", higher_is_better: true };
    expect(numericColorFor(10, rule)).toBe("green");
    expect(numericColorFor(2, rule)).toBe("red");
  });

  it("checks red before green when a value could satisfy both (misconfigured overlap)", () => {
    const rule = { green_cutoff: "5", red_cutoff: "8", higher_is_better: true };
    expect(numericColorFor(6, rule)).toBe("red");
  });

  it("falls back to amber when neither cutoff is hit", () => {
    const rule = { green_cutoff: "10", red_cutoff: "2", higher_is_better: true };
    expect(numericColorFor(5, rule)).toBe("amber");
  });

  it("treats a missing cutoff as no rule on that side", () => {
    const rule = { green_cutoff: "", red_cutoff: "2", higher_is_better: false };
    expect(numericColorFor(1, rule)).toBe("amber");
    expect(numericColorFor(3, rule)).toBe("red");
  });
});
