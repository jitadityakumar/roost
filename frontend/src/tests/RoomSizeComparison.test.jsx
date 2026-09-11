import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RoomSizeComparison from "../components/RoomSizeComparison.jsx";

function fixture(overrides = {}) {
  return {
    summary: {
      indoor: { baseline: 606, listing: 601, delta_pct: -0.8 },
      outdoor: { baseline: 288, listing: 22, delta_pct: -92.4 },
      grand: { baseline: 894, listing: 623, delta_pct: -30.3 },
      floor_area_cross_check: null,
    },
    types: [
      {
        type: "bedroom",
        label: "Bedroom",
        baseline_total: 282,
        listing_total: 259,
        rooms: [
          { rank: 1, baseline_sqft: 145, listing_sqft: 122, delta_pct: -15.9 },
          { rank: 2, baseline_sqft: 137, listing_sqft: 91, delta_pct: -33.6 },
        ],
      },
    ],
    ...overrides,
  };
}

describe("RoomSizeComparison", () => {
  it("renders summary stat cards with baseline/listing/delta", () => {
    render(<RoomSizeComparison data={fixture()} />);
    expect(screen.getByText("Indoor total")).toBeInTheDocument();
    expect(screen.getByText("601 sq ft")).toBeInTheDocument();
    expect(screen.getByText("vs 606")).toBeInTheDocument();
    expect(screen.getByText("-0.8%")).toBeInTheDocument();
  });

  it("renders one group per room type with paired room rows", () => {
    render(<RoomSizeComparison data={fixture()} />);
    expect(screen.getByText("Bedroom")).toBeInTheDocument();
    expect(screen.getByText("-15.9%")).toBeInTheDocument();
    expect(screen.getByText("-33.6%")).toBeInTheDocument();
    expect(screen.getByText("122 sq ft")).toBeInTheDocument();
    expect(screen.getByText("145 sq ft")).toBeInTheDocument();
  });

  it('renders "new" for a room only the listing has', () => {
    const data = fixture({
      types: [
        {
          type: "hallway_storage",
          label: "Hallway / Storage",
          baseline_total: 0,
          listing_total: 89,
          rooms: [{ rank: 1, baseline_sqft: null, listing_sqft: 89, delta_pct: null }],
        },
      ],
    });
    render(<RoomSizeComparison data={data} />);
    expect(screen.getByText("new")).toBeInTheDocument();
    expect(screen.getByText("— none")).toBeInTheDocument();
  });

  it('renders "n/a" for a room only the baseline has', () => {
    const data = fixture({
      types: [
        {
          type: "outdoor",
          label: "Outdoor Space",
          baseline_total: 259,
          listing_total: 0,
          rooms: [{ rank: 1, baseline_sqft: 259, listing_sqft: null, delta_pct: null }],
        },
      ],
    });
    render(<RoomSizeComparison data={data} />);
    expect(screen.getByText("n/a")).toBeInTheDocument();
  });

  it("renders the floor area cross-check row only when present", () => {
    const { rerender } = render(<RoomSizeComparison data={fixture()} />);
    expect(screen.queryByText("Traced vs stated floor area")).not.toBeInTheDocument();

    const withCrossCheck = fixture({
      summary: {
        ...fixture().summary,
        floor_area_cross_check: { traced_indoor: 601, stated_floor_area: 650, delta_pct: -7.5 },
      },
    });
    rerender(<RoomSizeComparison data={withCrossCheck} />);
    expect(screen.getByText("Traced vs stated floor area")).toBeInTheDocument();
  });
});
