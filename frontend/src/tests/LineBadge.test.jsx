import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LineBadge from "../components/LineBadge.jsx";

vi.mock("../components/networkLogos.js", () => ({
  logoUrlForType: (t) => (t === "LONDON_UNDERGROUND" ? "/tube.svg" : undefined),
}));

describe("LineBadge", () => {
  it("defaults to auto sizing and pins lg / sm via class", () => {
    const { container, rerender } = render(<LineBadge name="Northern" />);
    expect(container.firstChild).toHaveClass("line-badge-auto");
    rerender(<LineBadge name="Northern" size="sm" />);
    expect(container.firstChild).toHaveClass("line-badge-sm");
    rerender(<LineBadge name="Northern" size="lg" />);
    expect(container.firstChild).toHaveClass("line-badge-lg");
  });

  it("shows the logo cell when a logo exists and omits it otherwise", () => {
    const { container, rerender } = render(<LineBadge name="Northern" />);
    expect(container.querySelector("img.line-badge-logo")).toHaveAttribute("src", "/tube.svg");
    rerender(<LineBadge name="Thameslink" />);
    expect(container.querySelector("img")).toBeNull();
  });

  it("exposes the full name on the small tile and applies a colour override", () => {
    render(<LineBadge name="Northern" color="#112233" />);
    expect(screen.getByRole("img", { name: "Northern" })).toHaveAttribute("data-label", "Northern");
    expect(screen.getByText("Northern")).toHaveStyle({ backgroundColor: "#112233" });
  });
});
