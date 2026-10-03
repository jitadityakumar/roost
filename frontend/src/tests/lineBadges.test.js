import { describe, expect, it } from "vitest";
import { lookupLineBadge, textColorFor, wcagText } from "../lineBadges.js";

describe("lookupLineBadge", () => {
  it("finds tube lines and operators by name, case-insensitively", () => {
    expect(lookupLineBadge("Waterloo & City")).toMatchObject({ code: "W&C", group: "underground" });
    expect(lookupLineBadge("south western railway")).toMatchObject({ code: "SW", group: "rail" });
  });

  it("maps data-source aliases", () => {
    expect(lookupLineBadge("Elizabeth Line").code).toBe("ELI");
    expect(lookupLineBadge("LNR & WMR").name).toBe("London Northwestern Railway");
  });

  it("falls back to a neutral grey tile for unknown names", () => {
    expect(lookupLineBadge("Mystery Rail")).toMatchObject({ code: "MY", color: "#888888", group: "rail" });
  });
});

describe("text colour", () => {
  it("uses the luminance rule for tube tiles", () => {
    expect(textColorFor(lookupLineBadge("Northern"))).toBe("#fff");
    expect(textColorFor(lookupLineBadge("Circle"))).toBe("#000");
  });

  it("uses WCAG contrast for rail tiles", () => {
    expect(wcagText("#000000")).toBe("#fff");
    expect(wcagText("#FFFFFF")).toBe("#000");
    expect(textColorFor(lookupLineBadge("Thameslink"))).toBe("#000");
  });
});
