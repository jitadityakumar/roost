import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NearestStations from "../components/NearestStations.jsx";

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

  it("omits the distance when it is missing or not a number", () => {
    render(<NearestStations stations={[{ name: "Sampleton", distance: null, types: [] }]} />);

    expect(screen.getByText("Sampleton")).toBeInTheDocument();
    expect(screen.queryByText(/mi/)).not.toBeInTheDocument();
  });
});
