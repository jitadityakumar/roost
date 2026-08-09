import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Crime from "../components/Crime.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { crime: vi.fn() },
}));

function makeComparison(scoreRatio) {
  return {
    categories: [
      { category: "burglary", residential: true, candidate_count: 6, baseline_count: 3, ratio: 2.0 },
      { category: "drugs", residential: false, candidate_count: 2, baseline_count: 4, ratio: 0.5 },
    ],
    candidate_total: 8,
    baseline_total: 7,
    total_ratio: 8 / 7,
    candidate_residential: 6,
    baseline_residential: 3,
    residential_ratio: 2.0,
    candidate_footfall: 2,
    baseline_footfall: 4,
    footfall_ratio: 0.5,
    candidate_score: 4.8,
    baseline_score: 2.4,
    score_ratio: scoreRatio,
  };
}

describe("Crime", () => {
  it("shows a waiting message when the listing isn't ready yet", () => {
    render(<Crime listingId={1} ready={false} />);
    expect(screen.getByText(/Waiting for listing details/)).toBeInTheDocument();
    expect(api.crime).not.toHaveBeenCalled();
  });

  it("shows a message when the listing has no postcode", async () => {
    api.crime.mockResolvedValue({ unavailable: "listing has no postcode", baselines: [] });
    render(<Crime listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText("listing has no postcode")).toBeInTheDocument());
  });

  it("prompts to add a baseline when none are configured", async () => {
    api.crime.mockResolvedValue({ unavailable: null, baselines: [] });
    render(<Crime listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText(/Add a baseline in Admin/)).toBeInTheDocument());
  });

  it("shows a ratio badge per baseline in the collapsed view", async () => {
    api.crime.mockResolvedValue({
      unavailable: null,
      baselines: [
        { id: 1, label: "Home", postcode: "ZZ1 1AA", error: null, comparison: makeComparison(2.0) },
        { id: 2, label: "Old flat", postcode: "ZZ3 3CC", error: null, comparison: makeComparison(0.8) },
      ],
    });
    render(<Crime listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText("ZZ1 1AA")).toBeInTheDocument());
    expect(screen.getByText("2.0x")).toBeInTheDocument();
    expect(screen.getByText("ZZ3 3CC")).toBeInTheDocument();
    expect(screen.getByText("0.8x")).toBeInTheDocument();
  });

  it("shows a per-baseline error without failing the whole section", async () => {
    api.crime.mockResolvedValue({
      unavailable: null,
      baselines: [{ id: 1, label: "Home", postcode: "ZZ1 1AA", error: "boom", comparison: null }],
    });
    render(<Crime listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText("ZZ1 1AA")).toBeInTheDocument());
    expect(screen.getByTitle(/Couldn't load: boom/)).toBeInTheDocument();
  });

  it("expands to show the per-category table on click", async () => {
    api.crime.mockResolvedValue({
      unavailable: null,
      baselines: [
        { id: 1, label: "Home", postcode: "ZZ1 1AA", error: null, comparison: makeComparison(2.0) },
      ],
    });
    const user = userEvent.setup();
    render(<Crime listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("ZZ1 1AA")).toBeInTheDocument());
    expect(screen.queryByText("burglary")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show categories" }));
    expect(screen.getByText("burglary")).toBeInTheDocument();
    expect(screen.getByText("3 (2.0x)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide categories" }));
    expect(screen.queryByText("burglary")).not.toBeInTheDocument();
  });

  it("expands without crashing when baselines have different category sets", async () => {
    // "public-order" only appears in Old flat's comparison (the listing and
    // Home both have zero of it, so score.compare's category union drops it
    // from Home's list entirely) -- Home's cell for that row must default
    // to 0/n-a rather than crashing on a missing row.
    const homeComparison = {
      ...makeComparison(2.0),
      categories: [
        { category: "burglary", residential: true, candidate_count: 6, baseline_count: 3, ratio: 2.0 },
      ],
    };
    const oldFlatComparison = {
      ...makeComparison(0.8),
      categories: [
        { category: "burglary", residential: true, candidate_count: 6, baseline_count: 3, ratio: 2.0 },
        { category: "public-order", residential: false, candidate_count: 0, baseline_count: 5, ratio: 0 },
      ],
    };
    api.crime.mockResolvedValue({
      unavailable: null,
      baselines: [
        { id: 1, label: "Home", postcode: "ZZ1 1AA", error: null, comparison: homeComparison },
        { id: 2, label: "Old flat", postcode: "ZZ3 3CC", error: null, comparison: oldFlatComparison },
      ],
    });
    const user = userEvent.setup();
    render(<Crime listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("ZZ1 1AA")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Show categories" }));

    expect(screen.getByText("public-order")).toBeInTheDocument();
    const row = screen.getByText("public-order").closest("tr");
    expect(row).toHaveTextContent("0 (n/a)");
    expect(row).toHaveTextContent("5 (0.0x)");
  });

  it("shows a section-level error when the request itself fails", async () => {
    api.crime.mockRejectedValue(new Error("network down"));
    render(<Crime listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
