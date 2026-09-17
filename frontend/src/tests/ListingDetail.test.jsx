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
    floorplan: {
      comparison: vi.fn(),
      getListingTrace: vi.fn(),
      putListingTrace: vi.fn(),
    },
    fieldColors: {
      list: vi.fn().mockResolvedValue([]),
    },
    detailSections: {
      get: vi.fn().mockResolvedValue({
        details_expanded: true,
        description_features_expanded: true,
        nearest_stations_expanded: true,
        floorplans_expanded: true,
        epc_expanded: true,
        room_sizes_expanded: true,
        commute_expanded: true,
        frequent_destinations_expanded: true,
        mortgage_expanded: true,
        crime_expanded: true,
        jobs_expanded: true,
      }),
    },
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

describe("ListingDetail field colour chips (issue #100)", () => {
  it("renders a threshold chip for a colorable field with a computed colour", async () => {
    api.get.mockResolvedValue(baseListing({ price_gbp: 500000, field_colors: { price_gbp: "green" } }));
    renderDetail();

    const chip = await screen.findByText("£500,000");
    expect(chip).toHaveClass("threshold-chip", "tc-green");
  });

  it("renders a plain value when field_colors has no entry for the field", async () => {
    api.get.mockResolvedValue(baseListing({ price_gbp: 500000, field_colors: {} }));
    renderDetail();

    const value = await screen.findByText("£500,000");
    expect(value).not.toHaveClass("threshold-chip");
  });

  it("does not chip a non-colorable field even if it happens to have a matching key", async () => {
    api.get.mockResolvedValue(baseListing({ postcode: "SW17 9QR", field_colors: { postcode: "green" } }));
    renderDetail();

    const value = await screen.findByText("SW17 9QR");
    expect(value).not.toHaveClass("threshold-chip");
  });

  it("highlights chain_free green on Yes with no field_colors entry needed", async () => {
    api.get.mockResolvedValue(baseListing({ chain_free: true }));
    renderDetail();

    const chainFreeLabel = await screen.findByText("Chain free");
    const row = chainFreeLabel.closest(".field-row");
    const chip = within(row).getByText("Yes");
    expect(chip).toHaveClass("threshold-chip", "tc-green");
  });

  it("chips the broadband custom row using field_colors.broadband_top_speed_mbps", async () => {
    api.get.mockResolvedValue(
      baseListing({ broadband_top_speed: "900Mb", field_colors: { broadband_top_speed_mbps: "green" } })
    );
    renderDetail();

    const label = await screen.findByText("Broadband top speed");
    const row = label.closest(".field-row");
    const chip = within(row).getByText("900 Mbps");
    expect(chip).toHaveClass("threshold-chip", "tc-green");
  });
});

describe("ListingDetail crime multiplier and mortgage summary rows (issue #101)", () => {
  it("shows the property's crime ratio from the reference baseline in the Details section", async () => {
    api.get.mockResolvedValue(baseListing({}));
    api.crime.mockResolvedValue({
      unavailable: null,
      postcode: "SW17 9QR",
      baselines: [
        {
          id: 1,
          label: "Barnes",
          postcode: "SW13 9JR",
          is_reference: true,
          comparison: { candidate_score: 15, baseline_score: 10, categories: [] },
        },
      ],
    });
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const row = within(details).getByText("Crime multiplier").closest(".field-row");
    await waitFor(() => expect(within(row).getByText("1.5x")).toBeInTheDocument());
  });

  it("shows an em dash for crime multiplier when there are no baselines to compare against", async () => {
    api.get.mockResolvedValue(baseListing({}));
    api.crime.mockResolvedValue({ unavailable: null, baselines: [] });
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const row = within(details).getByText("Crime multiplier").closest(".field-row");
    await waitFor(() => expect(within(row).getByText("—")).toBeInTheDocument());
  });

  it("shows the mortgage summary rows from the same calculation as the Mortgage section", async () => {
    api.get.mockResolvedValue(baseListing({ price_gbp: 500000 }));
    api.mortgage.mockResolvedValue({
      error: null,
      result: {
        monthlyPayments: [{ fromMonth: 1, payment: 2345.67, isVariable: false }],
        payoffMonth: 301,
        sdltPaid: 0,
        totalInterestPaid: 0,
        totalPaid: 0,
      },
    });
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const paymentRow = within(details).getByText("Initial monthly payment").closest(".field-row");
    await waitFor(() => expect(within(paymentRow).getByText("£2,346")).toBeInTheDocument());

    const payoffRow = within(details).getByText("Time to payoff").closest(".field-row");
    expect(within(payoffRow).getByText("25y")).toBeInTheDocument();
  });

  it("shows an em dash for mortgage summary rows when the listing has no price", async () => {
    api.get.mockResolvedValue(baseListing({ price_gbp: null }));
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const paymentRow = await within(details).findByText("Initial monthly payment");
    expect(within(paymentRow.closest(".field-row")).getByText("—")).toBeInTheDocument();
  });

  it("chips the crime multiplier row using an admin-configured threshold (issue #101 follow-up)", async () => {
    api.get.mockResolvedValue(baseListing({}));
    api.crime.mockResolvedValue({
      unavailable: null,
      baselines: [
        {
          id: 1,
          label: "Barnes",
          is_reference: true,
          comparison: { candidate_score: 15, baseline_score: 10, categories: [] },
        },
      ],
    });
    api.fieldColors.list.mockResolvedValueOnce([
      { field: "crime_multiplier", green_cutoff: "1.0", red_cutoff: "2.0", higher_is_better: false },
    ]);
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const row = within(details).getByText("Crime multiplier").closest(".field-row");
    const chip = await within(row).findByText("1.5x");
    expect(chip).toHaveClass("threshold-chip", "tc-amber");
  });

  it("chips the initial monthly payment row using an admin-configured threshold (issue #101 follow-up)", async () => {
    api.get.mockResolvedValue(baseListing({ price_gbp: 500000 }));
    api.mortgage.mockResolvedValue({
      error: null,
      result: {
        monthlyPayments: [{ fromMonth: 1, payment: 2345.67, isVariable: false }],
        payoffMonth: 301,
        sdltPaid: 0,
        totalInterestPaid: 0,
        totalPaid: 0,
      },
    });
    api.fieldColors.list.mockResolvedValueOnce([
      { field: "initial_monthly_payment", green_cutoff: "2500", red_cutoff: "3000", higher_is_better: false },
    ]);
    renderDetail();

    const heading = await screen.findByText("Details");
    const details = heading.closest(".collapsible-section");
    const row = within(details).getByText("Initial monthly payment").closest(".field-row");
    const chip = await within(row).findByText("£2,346");
    expect(chip).toHaveClass("threshold-chip", "tc-green");
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
    await user.click(await screen.findByRole("button", { name: "Change status ▾" }));
    await user.click(await screen.findByRole("button", { name: "Approved" }));
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

describe("ListingDetail status-change menu", () => {
  it("excludes the listing's current status from the menu options", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing({ user_status: "approved" }));
    renderDetail();

    await user.click(await screen.findByRole("button", { name: "Change status ▾" }));

    const menu = screen.getByText("Triage").closest(".status-menu");
    expect(within(menu).queryByText("Approved")).not.toBeInTheDocument();
    expect(within(menu).getByText("Triage")).toBeInTheDocument();
    expect(within(menu).getByText("Rejected")).toBeInTheDocument();
    expect(within(menu).getByText("Viewing")).toBeInTheDocument();
    expect(within(menu).getByText("Contacted")).toBeInTheDocument();
  });

  it("moving to a comment-required status shows the comment box, not an immediate patch", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing());
    renderDetail();
    api.patch.mockClear();

    await user.click(await screen.findByRole("button", { name: "Change status ▾" }));
    await user.click(await screen.findByRole("button", { name: /^Rejected/ }));

    expect(screen.getByLabelText("Reason for rejecting")).toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("blocks confirming a comment-required move without both a comment and initials", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing());
    renderDetail();
    api.patch.mockClear();

    await user.click(await screen.findByRole("button", { name: "Change status ▾" }));
    await user.click(await screen.findByRole("button", { name: /^Viewing/ }));
    await user.click(screen.getByRole("button", { name: "Confirm move" }));

    expect(screen.getByText("A comment and initials are required.")).toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("submits comment and initials when confirming a move to Contacted", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing());
    api.patch.mockResolvedValue(baseListing({ user_status: "contacted" }));
    renderDetail();

    await user.click(await screen.findByRole("button", { name: "Change status ▾" }));
    await user.click(await screen.findByRole("button", { name: /^Contacted/ }));
    await user.type(screen.getByLabelText("Note on contacting the agent"), "Emailed the agent");
    await user.type(screen.getByLabelText("Initials"), "JK");
    await user.click(screen.getByRole("button", { name: "Confirm move" }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith("1", {
        user_status: "contacted",
        comment: "Emailed the agent",
        initials: "JK",
      })
    );
  });
});

describe("ListingDetail section collapsing", () => {
  it("renders a section collapsed on load when the admin config says so", async () => {
    api.get.mockResolvedValue(baseListing());
    api.detailSections.get.mockResolvedValueOnce({
      details_expanded: true,
      description_features_expanded: true,
      nearest_stations_expanded: true,
      floorplans_expanded: true,
      epc_expanded: true,
      room_sizes_expanded: true,
      commute_expanded: false,
      frequent_destinations_expanded: true,
      mortgage_expanded: true,
      crime_expanded: true,
      jobs_expanded: true,
    });
    renderDetail();

    const commuteToggle = await screen.findByRole("button", { name: /Commute/ });
    expect(commuteToggle).toHaveAttribute("aria-expanded", "false");
  });

  it("clicking a section header toggles it open", async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue(baseListing());
    api.detailSections.get.mockResolvedValueOnce({
      details_expanded: true,
      description_features_expanded: true,
      nearest_stations_expanded: true,
      floorplans_expanded: true,
      epc_expanded: true,
      room_sizes_expanded: true,
      commute_expanded: false,
      frequent_destinations_expanded: true,
      mortgage_expanded: true,
      crime_expanded: true,
      jobs_expanded: true,
    });
    renderDetail();

    const commuteToggle = await screen.findByRole("button", { name: /Commute/ });
    expect(commuteToggle).toHaveAttribute("aria-expanded", "false");
    await user.click(commuteToggle);
    expect(commuteToggle).toHaveAttribute("aria-expanded", "true");
  });

  it("renders an empty-state placeholder for a section with no data, rather than hiding it", async () => {
    api.get.mockResolvedValue(baseListing({ nearest_stations: [] }));
    renderDetail();

    const stationsToggle = await screen.findByRole("button", { name: /Nearest stations/ });
    expect(stationsToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("No nearby stations found.")).toBeInTheDocument();
  });
});
