import { describe, expect, it } from "vitest";
import { LINE_BADGES, lookupLineBadge, operatorNames, textColorFor, wcagText } from "../lineBadges.js";

describe("lookupLineBadge", () => {
  it("finds tube lines and operators by name, case-insensitively", () => {
    expect(lookupLineBadge("Waterloo & City")).toMatchObject({ code: "W&C", group: "underground" });
    expect(lookupLineBadge("south western railway")).toMatchObject({ code: "SW", group: "rail" });
  });

  it("maps data-source aliases", () => {
    expect(lookupLineBadge("Elizabeth Line").code).toBe("ELI");
    expect(lookupLineBadge("elizabeth LINE").name).toBe("Elizabeth line");
  });

  it("falls back to a neutral grey tile for unknown names", () => {
    expect(lookupLineBadge("Mystery Rail")).toMatchObject({ code: "MYS", color: "#888888", group: "other", logoType: undefined });
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

describe("lookup details", () => {
  it("trims, tolerates empty input, and lets a colour override win", () => {
    expect(lookupLineBadge("  Northern ").code).toBe("NOR");
    expect(lookupLineBadge(null).code).toBe("?");
    expect(lookupLineBadge("Northern", "#123456").color).toBe("#123456");
  });

  it("table has unique names and valid hex colours", () => {
    const names = LINE_BADGES.map((b) => b.name);
    expect(new Set(names).size).toBe(names.length);
    LINE_BADGES.forEach((b) => expect(b.color).toMatch(/^#[0-9A-F]{6}$/i));
  });
});

describe("operatorNames", () => {
  it("splits the comma-joined title and expands the combined LNR & WMR name", () => {
    expect(operatorNames("Southeastern, Thameslink")).toEqual(["Southeastern", "Thameslink"]);
    expect(operatorNames("LNR & WMR")).toEqual(["London Northwestern Railway", "West Midlands Railway"]);
    expect(operatorNames("")).toEqual([]);
    expect(operatorNames(undefined)).toEqual([]);
  });
});
