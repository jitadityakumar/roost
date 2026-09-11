import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RoomSizeComparison from "../components/RoomSizeComparison.jsx";

function fixture(overrides = {}) {
  return {
    summary: {
      indoor: { baseline: 606, listing: 601, delta_pct: -0.8 },
      outdoor: { baseline: 288, listing: 22, delta_pct: -92.4 },
      grand: { baseline: 894, listing: 623, delta_pct: -30.3 },
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

  it("scales every room's bars in a type group against the group's overall max, not just its own pair", () => {
    // fixture's bedroom group: rank 1 {145, 122}, rank 2 {137, 91} -- the
    // group max is 145 (rank 1's baseline). Rank 2's own pair-max (137) is
    // smaller, so its baseline bar must read as < 100% of the track, not
    // pinned to 100% the way a per-room scale would render it.
    const { container } = render(<RoomSizeComparison data={fixture()} />);
    const rows = container.querySelectorAll(".rs-room");
    const [rank1Base, rank1Listing] = rows[0].querySelectorAll(".rs-bar-fill");
    const [rank2Base, rank2Listing] = rows[1].querySelectorAll(".rs-bar-fill");
    expect(parseFloat(rank1Base.style.width)).toBeCloseTo(100, 1);
    expect(parseFloat(rank1Listing.style.width)).toBeCloseTo((122 / 145) * 100, 1);
    expect(parseFloat(rank2Base.style.width)).toBeCloseTo((137 / 145) * 100, 1);
    expect(parseFloat(rank2Listing.style.width)).toBeCloseTo((91 / 145) * 100, 1);
  });

  it("includes listing values (not just baseline) when finding the group's scale-setting max", () => {
    const data = fixture({
      types: [
        {
          type: "bedroom",
          label: "Bedroom",
          baseline_total: 100,
          listing_total: 200,
          rooms: [{ rank: 1, baseline_sqft: 100, listing_sqft: 200, delta_pct: 100 }],
        },
      ],
    });
    const { container } = render(<RoomSizeComparison data={data} />);
    const [baseFill, listingFill] = container.querySelectorAll(".rs-bar-fill");
    expect(parseFloat(baseFill.style.width)).toBeCloseTo(50, 1);
    expect(parseFloat(listingFill.style.width)).toBeCloseTo(100, 1);
  });

  it("doesn't let a one-sided room's null side pull down the group max for the rest of the group", () => {
    const data = fixture({
      types: [
        {
          type: "bedroom",
          label: "Bedroom",
          baseline_total: 145,
          listing_total: 122,
          rooms: [
            { rank: 1, baseline_sqft: 145, listing_sqft: 122, delta_pct: -15.9 },
            { rank: 2, baseline_sqft: null, listing_sqft: 30, delta_pct: null },
          ],
        },
      ],
    });
    const { container } = render(<RoomSizeComparison data={data} />);
    const rows = container.querySelectorAll(".rs-room");
    const rank1Base = rows[0].querySelector(".rs-bar-fill.base");
    const rank2Listing = rows[1].querySelector(".rs-bar-fill.listing");
    expect(parseFloat(rank1Base.style.width)).toBeCloseTo(100, 1);
    expect(parseFloat(rank2Listing.style.width)).toBeCloseTo((30 / 145) * 100, 1);
  });

  it('renders "new" for a room only the listing has', () => {
    const data = fixture({
      types: [
        {
          type: "outdoor",
          label: "Outdoor Space",
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

  it("renders the hallway/storage remainder group as a single bar row, showing n/a when a side's total is unknown", () => {
    const data = fixture({
      types: [
        {
          type: "hallway_storage",
          label: "Hallway / Storage",
          baseline_total: 89,
          listing_total: null,
          rooms: [{ rank: 1, baseline_sqft: 89, listing_sqft: null, delta_pct: null }],
        },
      ],
    });
    const { container } = render(<RoomSizeComparison data={data} />);
    expect(screen.getByText("Hallway / Storage")).toBeInTheDocument();
    expect(container.querySelector(".rs-group-total").textContent).toBe("n/a listing vs 89 sq ft yours");
    expect(screen.getByText(/Not traced directly/)).toBeInTheDocument();
    expect(container.querySelectorAll(".rs-room")).toHaveLength(1);
    expect(screen.getByText("89 sq ft")).toBeInTheDocument();
    // an unknown side here means "internal sq ft wasn't entered", not "this
    // space doesn't exist" -- must render as a neutral "n/a", never the
    // green "new" badge used for a real one-sided room in other types.
    const badge = container.querySelector(".rs-room-delta");
    expect(badge.textContent).toBe("n/a");
    expect(badge.className).toContain("neutral");
    expect(badge.className).not.toContain("good");
  });

  it("clamps a negative hallway/storage remainder's bar width on both sides instead of breaking, while still showing the real numbers", () => {
    const data = fixture({
      types: [
        {
          type: "hallway_storage",
          label: "Hallway / Storage",
          baseline_total: -5,
          listing_total: -20,
          rooms: [{ rank: 1, baseline_sqft: -5, listing_sqft: -20, delta_pct: null }],
        },
      ],
    });
    const { container } = render(<RoomSizeComparison data={data} />);
    expect(screen.getByText("-5 sq ft")).toBeInTheDocument();
    expect(screen.getByText("-20 sq ft")).toBeInTheDocument();
    expect(container.querySelector(".rs-bar-fill.base").style.width).toBe("0%");
    expect(container.querySelector(".rs-bar-fill.listing").style.width).toBe("0%");
    // a negative baseline (mismatch) must never be colored as an
    // improvement -- the backend suppresses delta_pct to null in this case,
    // which must render neutral, not the green "new" badge.
    const badge = container.querySelector(".rs-room-delta");
    expect(badge.textContent).toBe("n/a");
    expect(badge.className).not.toContain("good");
  });

  it("renders exactly 3 summary stat cards (indoor/outdoor/grand), no floor-area cross-check", () => {
    const { container } = render(<RoomSizeComparison data={fixture()} />);
    expect(container.querySelectorAll(".rs-stat")).toHaveLength(3);
    expect(screen.queryByText("Traced vs stated floor area")).not.toBeInTheDocument();
  });

  it("puts a stat card's delta badge on its own line, after the value/baseline line", () => {
    const { container } = render(<RoomSizeComparison data={fixture()} />);
    const stat = container.querySelector(".rs-stat");
    const figs = stat.querySelector(".rs-stat-figs");
    const delta = stat.querySelector(".rs-stat-delta");
    expect(delta.parentElement).toBe(stat);
    expect(figs.contains(delta)).toBe(false);
  });
});
