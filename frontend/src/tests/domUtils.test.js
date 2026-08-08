import { describe, expect, it } from "vitest";
import { isTypingTarget } from "../components/domUtils.js";

describe("isTypingTarget", () => {
  it("returns false for null/undefined", () => {
    expect(isTypingTarget(null)).toBe(false);
    expect(isTypingTarget(undefined)).toBe(false);
  });

  it.each(["INPUT", "TEXTAREA", "SELECT"])("returns true for a %s element", (tagName) => {
    expect(isTypingTarget({ tagName })).toBe(true);
  });

  it("returns true for a contentEditable element", () => {
    expect(isTypingTarget({ tagName: "DIV", isContentEditable: true })).toBe(true);
  });

  it("returns false for a plain element", () => {
    expect(isTypingTarget({ tagName: "DIV", isContentEditable: false })).toBe(false);
  });
});
