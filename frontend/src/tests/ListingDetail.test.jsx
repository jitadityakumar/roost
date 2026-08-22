import { render, screen, waitFor, within } from "@testing-library/react";
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

describe("ListingDetail council tax rows", () => {
  it("renders the estimate and council name as read-only rows", async () => {
    api.get.mockResolvedValue(
      baseListing({
        council_tax_band: "D",
        council_tax_monthly_est: 195,
        admin_district: "Wandsworth",
      })
    );
    renderDetail();

    await waitFor(() => expect(screen.getByText("£195/mo")).toBeInTheDocument());
    expect(screen.getByText("Wandsworth")).toBeInTheDocument();
    // Neither derived row has an edit control -- editMode is off by default,
    // but confirm there's no edit affordance even conceptually reachable:
    // both fields are `editable: false` in FIELDS, unlike council_tax_band
    // itself right above them.
    expect(screen.queryByRole("button", { name: "✎" })).not.toBeInTheDocument();
  });

  it("shows an em dash for the estimate when no rate is set", async () => {
    api.get.mockResolvedValue(baseListing({ council_tax_band: "D", council_tax_monthly_est: null }));
    renderDetail();

    await waitFor(() => expect(screen.getByText(/View on Rightmove/)).toBeInTheDocument());
  });

  it("updates the estimate after editing council_tax_band, without a reload", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(
      baseListing({ council_tax_band: "C", council_tax_monthly_est: 150, admin_district: "Wandsworth" })
    );
    api.patch.mockResolvedValue(
      baseListing({ council_tax_band: "D", council_tax_monthly_est: 195, admin_district: "Wandsworth" })
    );
    renderDetail();

    await waitFor(() => expect(screen.getByText("£150/mo")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Edit" }));

    // council_tax_band is editable; the est./council rows next to it are
    // not (no edit button) -- grab it by its row rather than assuming
    // index stability among the page's other editable fields.
    const bandRow = screen.getByText("Council tax band").closest(".field-row");
    await user.click(within(bandRow).getByRole("button", { name: "✎" }));
    await user.clear(within(bandRow).getByRole("textbox"));
    await user.type(within(bandRow).getByRole("textbox"), "D");
    await user.click(within(bandRow).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("1", { fields: { council_tax_band: "D" } })
    );
    await waitFor(() => expect(screen.getByText("£195/mo")).toBeInTheDocument());
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
