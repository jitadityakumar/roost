import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import NearestStations from "../components/NearestStations.jsx";
import { logoUrlForType } from "../components/networkLogos.js";

// Deterministic: exercise the letter-badge fallback regardless of whether
// the gitignored real logo files happen to be present on the machine
// running the tests. Logo-vs-fallback selection itself is covered below.
vi.mock("../components/networkLogos.js", () => ({
  logoUrlForType: vi.fn(() => undefined),
}));

describe("NearestStations", () => {
  it("renders nothing for an empty or missing list", () => {
    const { container: emptyContainer } = render(<NearestStations stations={[]} />);
    expect(emptyContainer).toBeEmptyDOMElement();

    const { container: missingContainer } = render(<NearestStations stations={null} />);
    expect(missingContainer).toBeEmptyDOMElement();
  });

  it("renders the station name and formatted distance", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 0.3, types: ["NATIONAL_TRAIN"] }]} />);

    expect(screen.getByText("Sampleton")).toBeInTheDocument();
    expect(screen.getByText("0.30 mi")).toBeInTheDocument();
  });

  it("shows a known badge letter for a recognized transport type", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 1, types: ["LONDON_UNDERGROUND"] }]} />);

    expect(screen.getByTitle("Underground")).toHaveTextContent("U");
  });

  it("falls back to the default badge for an unrecognized transport type", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 1, types: ["HOVERCRAFT"] }]} />);

    expect(screen.getByTitle("Station")).toHaveTextContent("?");
  });

  it("shows the DLR badge for Rightmove's real LIGHT_RAILWAY type, not a stale DLR key", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 1, types: ["LIGHT_RAILWAY"] }]} />);

    expect(screen.getByTitle("DLR")).toHaveTextContent("D");
  });

  it("shows the Tram badge for Rightmove's real TRAM type, not a stale TRAMLINK key", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 1, types: ["TRAM"] }]} />);

    expect(screen.getByTitle("Tram")).toHaveTextContent("T");
  });

  it("omits the distance when it is missing or not a number", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: null, types: [] }]} />);

    expect(screen.getByText("Sampleton")).toBeInTheDocument();
    expect(screen.queryByText(/mi/)).not.toBeInTheDocument();
  });

  it("shows walking distance and time alongside the raw distance when stored", () => {
    render(
      <NearestStations
        stations={[
          {
            name: "Sampleton",
            distance: 0.3,
            types: ["NATIONAL_TRAIN"],
            walk_distance_meters: 845,
            walk_duration_seconds: 720,
          },
        ]}
      />
    );

    expect(screen.getByText("0.30 mi")).toBeInTheDocument();
    expect(screen.getByText("845m · 12 min walk")).toBeInTheDocument();
  });

  it("omits walking distance and time when not stored, keeping the raw distance", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: 0.3, types: ["NATIONAL_TRAIN"] }]} />);

    expect(screen.getByText("0.30 mi")).toBeInTheDocument();
    expect(screen.queryByText(/min walk/)).not.toBeInTheDocument();
  });

  it("renders a real logo image instead of the letter badge when one is available", () => {
    vi.mocked(logoUrlForType).mockReturnValueOnce("/fake/underground.svg");

    render(<NearestStations stations={[{ name: "Sampleton", distance: 1, types: ["LONDON_UNDERGROUND"] }]} />);

    const img = screen.getByAltText("Underground");
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", "/fake/underground.svg");
    expect(screen.queryByText("U")).not.toBeInTheDocument();
  });
});
