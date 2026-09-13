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

  it("renders the station name and formatted straight-line distance", () => {
    render(
      <NearestStations stations={[{ name: "Sampleton", straight_line_meters: 300, types: ["NATIONAL_TRAIN"] }]} />
    );

    expect(screen.getByText("Sampleton")).toBeInTheDocument();
    expect(screen.getByText("300m")).toBeInTheDocument();
  });

  it("shows a known badge letter for a recognized transport type", () => {
    render(
      <NearestStations stations={[{ name: "Sampleton", straight_line_meters: 1000, types: ["LONDON_UNDERGROUND"] }]} />
    );

    expect(screen.getByTitle("Underground")).toHaveTextContent("U");
  });

  it("falls back to the default badge for an unrecognized transport type", () => {
    render(<NearestStations stations={[{ name: "Sampleton", straight_line_meters: 1000, types: ["HOVERCRAFT"] }]} />);

    expect(screen.getByTitle("Station")).toHaveTextContent("?");
  });

  it("shows the DLR badge for Rightmove's real LIGHT_RAILWAY type, not a stale DLR key", () => {
    render(
      <NearestStations stations={[{ name: "Sampleton", straight_line_meters: 1000, types: ["LIGHT_RAILWAY"] }]} />
    );

    expect(screen.getByTitle("DLR")).toHaveTextContent("D");
  });

  it("shows the Tram badge for Rightmove's real TRAM type, not a stale TRAMLINK key", () => {
    render(<NearestStations stations={[{ name: "Sampleton", straight_line_meters: 1000, types: ["TRAM"] }]} />);

    expect(screen.getByTitle("Tram")).toHaveTextContent("T");
  });

  it("omits the distance when it is missing", () => {
    render(<NearestStations stations={[{ name: "Sampleton", straight_line_meters: null, types: [] }]} />);

    expect(screen.getByText("Sampleton")).toBeInTheDocument();
    expect(screen.queryByText(/m$/)).not.toBeInTheDocument();
  });

  it("shows walking distance and time alongside the straight-line distance when stored", () => {
    render(
      <NearestStations
        stations={[
          {
            name: "Sampleton",
            straight_line_meters: 300,
            types: ["NATIONAL_TRAIN"],
            walk_distance_meters: 845,
            walk_duration_seconds: 720,
          },
        ]}
      />
    );

    expect(screen.getByText("300m")).toBeInTheDocument();
    expect(screen.getByText("845m · 12 min walk")).toBeInTheDocument();
  });

  it("renders the walk duration as a Google Maps link when walk_maps_url is present", () => {
    // Issue #76 -- same link format as the Commute section's walk_maps_url.
    render(
      <NearestStations
        stations={[
          {
            name: "Sampleton",
            straight_line_meters: 300,
            types: ["LONDON_UNDERGROUND"],
            walk_distance_meters: 845,
            walk_duration_seconds: 720,
            walk_maps_url: "https://www.google.com/maps/dir/?api=1&origin=1,2&destination=3,4&travelmode=walking",
          },
        ]}
      />
    );

    const link = screen.getByText("845m · 12 min walk ↗").closest("a");
    expect(link).toHaveAttribute(
      "href",
      "https://www.google.com/maps/dir/?api=1&origin=1,2&destination=3,4&travelmode=walking"
    );
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("renders the walk duration as plain text (no link) when walk_maps_url is absent", () => {
    render(
      <NearestStations
        stations={[
          {
            name: "Sampleton",
            straight_line_meters: 300,
            types: ["NATIONAL_TRAIN"],
            walk_distance_meters: 845,
            walk_duration_seconds: 720,
          },
        ]}
      />
    );

    expect(screen.getByText("845m · 12 min walk")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("omits walking distance and time when not stored, keeping the straight-line distance", () => {
    render(
      <NearestStations stations={[{ name: "Sampleton", straight_line_meters: 300, types: ["NATIONAL_TRAIN"] }]} />
    );

    expect(screen.getByText("300m")).toBeInTheDocument();
    expect(screen.queryByText(/min walk/)).not.toBeInTheDocument();
  });

  it("renders a real logo image instead of the letter badge when one is available", () => {
    vi.mocked(logoUrlForType).mockReturnValueOnce("/fake/underground.svg");

    render(
      <NearestStations stations={[{ name: "Sampleton", straight_line_meters: 1000, types: ["LONDON_UNDERGROUND"] }]} />
    );

    const img = screen.getByAltText("Underground");
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", "/fake/underground.svg");
    expect(screen.queryByText("U")).not.toBeInTheDocument();
  });

  it("translates multiple TfL modes into one row's worth of type badges", () => {
    // Same-station dedup case (issue #92) -- one candidate row can carry
    // several unioned Rightmove types (e.g. a station with both national
    // rail and tube).
    render(
      <NearestStations
        stations={[
          { name: "Wimbledon", straight_line_meters: 500, types: ["NATIONAL_TRAIN", "LONDON_UNDERGROUND"] },
        ]}
      />
    );

    expect(screen.getByTitle("National Rail")).toHaveTextContent("R");
    expect(screen.getByTitle("Underground")).toHaveTextContent("U");
  });
});
