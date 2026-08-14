import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import ListingDetail from "../components/ListingDetail.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    get: vi.fn(),
    patch: vi.fn(),
    jobs: vi.fn().mockResolvedValue([]),
    mediaList: vi.fn().mockResolvedValue({ photos: [], floorplans: [], epc: [] }),
    mediaUrl: (id, category, filename) => `/media/${id}/${category}/${filename}`,
    commute: vi.fn().mockResolvedValue({ stations: [] }),
    mortgage: vi.fn().mockResolvedValue({ result: null, error: null }),
    crime: vi.fn().mockResolvedValue({ unavailable: null, baselines: [] }),
    listingDestinations: vi.fn().mockResolvedValue([]),
    refreshListingDestinations: vi.fn().mockResolvedValue([]),
  },
}));

function baseListing(overrides = {}) {
  return {
    id: 1,
    url: "https://www.rightmove.co.uk/properties/1",
    extraction_status: "done",
    pipeline_status: null,
    user_status: "triage",
    edited_fields: {},
    standards_violations: [],
    ...overrides,
  };
}

function renderDetail(initialEntry = "/listings/1") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/listings/:id" element={<ListingDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

function renderDetailWithDestinations(initialEntry) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/listings/:id" element={<ListingDetail />} />
        <Route path="/triage" element={<p>Triage list</p>} />
        <Route path="/approved" element={<p>Approved list</p>} />
        <Route path="/rejected" element={<p>Rejected list</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ListingDetail standards warning", () => {
  it("renders a warning banner when the listing violates standards", async () => {
    api.get.mockResolvedValue(
      baseListing({
        standards_violations: [{ rule_id: 1, field: "floor_area_sqft", message: "Floor area is 650 (< 700)" }],
      })
    );
    renderDetail();

    await waitFor(() => expect(screen.getByText("Doesn't meet your standards")).toBeInTheDocument());
    expect(screen.getByText("Floor area is 650 (< 700)")).toBeInTheDocument();
  });

  it("shows no warning banner when there are no violations", async () => {
    api.get.mockResolvedValue(baseListing());
    renderDetail();

    await waitFor(() => expect(screen.getByText(/View on Rightmove/)).toBeInTheDocument());
    expect(screen.queryByText("Doesn't meet your standards")).not.toBeInTheDocument();
  });
});

describe("ListingDetail Google Maps link", () => {
  it("links to Google Maps with lat/lon when present", async () => {
    api.get.mockResolvedValue(baseListing({ latitude: 51.5074, longitude: -0.1278 }));
    renderDetail();

    const link = await screen.findByText(/Open in Google Maps/);
    expect(link.closest("a")).toHaveAttribute(
      "href",
      "https://www.google.com/maps/search/?api=1&query=51.5074,-0.1278"
    );
  });

  it("omits the Google Maps link when lat/lon are missing", async () => {
    api.get.mockResolvedValue(baseListing());
    renderDetail();

    await waitFor(() => expect(screen.getByText(/View on Rightmove/)).toBeInTheDocument());
    expect(screen.queryByText(/Open in Google Maps/)).not.toBeInTheDocument();
  });
});

describe("ListingDetail back button", () => {
  it("labels and navigates to the origin list from router state, even after approving", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing({ user_status: "triage" }));
    api.patch.mockResolvedValue(baseListing({ user_status: "approved" }));

    renderDetailWithDestinations({ pathname: "/listings/1", state: { from: "triage" } });

    const backBtn = await screen.findByRole("button", { name: "← Back to Triage" });
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("1", { user_status: "approved" }));

    // Origin list is remembered even though the listing's own status just changed.
    expect(screen.getByRole("button", { name: "← Back to Triage" })).toBeInTheDocument();
    await user.click(backBtn);
    expect(screen.getByText("Triage list")).toBeInTheDocument();
  });

  it("falls back to the listing's current status when there is no origin state", async () => {
    api.get.mockResolvedValue(baseListing({ user_status: "approved" }));

    renderDetailWithDestinations("/listings/1");

    const backBtn = await screen.findByRole("button", { name: "← Back to Approved" });
    expect(backBtn).toBeInTheDocument();
  });
});
