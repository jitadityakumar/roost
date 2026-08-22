import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminPage from "../components/AdminPage.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    standards: {
      list: vi.fn(),
      create: vi.fn(),
      patch: vi.fn(),
      remove: vi.fn(),
    },
    crimeBaselines: {
      list: vi.fn(),
      create: vi.fn(),
      remove: vi.fn(),
    },
    destinations: {
      list: vi.fn(),
      create: vi.fn(),
      remove: vi.fn(),
      searchStations: vi.fn(),
      backfillStatus: vi.fn(),
    },
    councilTax: {
      list: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    },
  },
}));

function renderAdmin() {
  return render(
    <MemoryRouter>
      <AdminPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  api.crimeBaselines.list.mockResolvedValue([]);
  api.destinations.list.mockResolvedValue([]);
  api.destinations.backfillStatus.mockResolvedValue({ status: "idle", done: 0, total: 0 });
  api.councilTax.list.mockResolvedValue([]);
});

async function gotoPanel(user, label) {
  await user.click(screen.getByRole("button", { name: new RegExp(`^${label}`) }));
}

describe("AdminPage", () => {
  it("shows an empty state when there are no rules", async () => {
    api.standards.list.mockResolvedValue([]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("No rules yet.")).toBeInTheDocument());
  });

  it("lists existing rules with a human-readable description", async () => {
    api.standards.list.mockResolvedValue([
      { id: 1, field: "floor_area_sqft", operator: "lt", value: "700", enabled: 1 },
    ]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("Floor area (sq ft) < 700")).toBeInTheDocument());
  });

  it("submits a new rule via the add-rule form", async () => {
    api.standards.list.mockResolvedValue([]);
    api.standards.create.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No rules yet.")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Value"), "700");
    await user.click(screen.getByRole("button", { name: "Add rule" }));

    await waitFor(() =>
      expect(api.standards.create).toHaveBeenCalledWith({ field: "price_gbp", operator: "lt", value: "700" })
    );
  });

  it("switches to a band picker for the EPC current field and submits the chosen band", async () => {
    api.standards.list.mockResolvedValue([]);
    api.standards.create.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No rules yet.")).toBeInTheDocument());

    await user.selectOptions(screen.getByDisplayValue("Price"), "epc_current");
    await user.selectOptions(screen.getByDisplayValue("C"), "D");
    await user.click(screen.getByRole("button", { name: "Add rule" }));

    await waitFor(() =>
      expect(api.standards.create).toHaveBeenCalledWith({ field: "epc_current", operator: "lt", value: "D" })
    );
  });

  it("toggles a rule's enabled state", async () => {
    api.standards.list.mockResolvedValue([
      { id: 1, field: "cash_only", operator: "eq", value: "true", enabled: 1 },
    ]);
    api.standards.patch.mockResolvedValue({});
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("Disable")).toBeInTheDocument());
    await user.click(screen.getByText("Disable"));

    await waitFor(() => expect(api.standards.patch).toHaveBeenCalledWith(1, { enabled: false }));
  });

  it("deletes a rule", async () => {
    api.standards.list.mockResolvedValue([
      { id: 1, field: "cash_only", operator: "eq", value: "true", enabled: 1 },
    ]);
    api.standards.remove.mockResolvedValue(null);
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByLabelText("Delete rule")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Delete rule"));

    await waitFor(() => expect(api.standards.remove).toHaveBeenCalledWith(1));
  });

  it("shows an empty state when there are no crime baselines", async () => {
    api.standards.list.mockResolvedValue([]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("No baselines yet.")).toBeInTheDocument());
  });

  it("lists existing crime baselines", async () => {
    api.standards.list.mockResolvedValue([]);
    api.crimeBaselines.list.mockResolvedValue([{ id: 1, label: "Home", postcode: "ZZ1 1AA" }]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("Home — ZZ1 1AA")).toBeInTheDocument());
  });

  it("submits a new crime baseline via the add-baseline form", async () => {
    api.standards.list.mockResolvedValue([]);
    api.crimeBaselines.list.mockResolvedValue([]);
    api.crimeBaselines.create.mockResolvedValue({ id: 1, label: "Home", postcode: "ZZ1 1AA" });
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No baselines yet.")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Label (e.g. Home)"), "Home");
    await user.type(screen.getByPlaceholderText("Postcode"), "ZZ1 1AA");
    await user.click(screen.getByRole("button", { name: "Add baseline" }));

    await waitFor(() =>
      expect(api.crimeBaselines.create).toHaveBeenCalledWith({ label: "Home", postcode: "ZZ1 1AA" })
    );
  });

  it("surfaces a create-baseline error inline", async () => {
    api.standards.list.mockResolvedValue([]);
    api.crimeBaselines.list.mockResolvedValue([]);
    api.crimeBaselines.create.mockRejectedValue(new Error("postcode not found"));
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No baselines yet.")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("Label (e.g. Home)"), "Home");
    await user.type(screen.getByPlaceholderText("Postcode"), "NOTREAL");
    await user.click(screen.getByRole("button", { name: "Add baseline" }));

    await waitFor(() => expect(screen.getByText("postcode not found")).toBeInTheDocument());
  });

  it("deletes a crime baseline", async () => {
    api.standards.list.mockResolvedValue([]);
    api.crimeBaselines.list.mockResolvedValue([{ id: 1, label: "Home", postcode: "ZZ1 1AA" }]);
    api.crimeBaselines.remove.mockResolvedValue(null);
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByLabelText("Delete baseline")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Delete baseline"));

    await waitFor(() => expect(api.crimeBaselines.remove).toHaveBeenCalledWith(1));
  });

  it("hides the add-baseline form once 3 baselines exist", async () => {
    api.standards.list.mockResolvedValue([]);
    api.crimeBaselines.list.mockResolvedValue([
      { id: 1, label: "A", postcode: "ZZ1 1AA" },
      { id: 2, label: "B", postcode: "ZZ3 3CC" },
      { id: 3, label: "C", postcode: "ZZ4 4DD" },
    ]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("A — ZZ1 1AA")).toBeInTheDocument());
    expect(screen.queryByPlaceholderText("Postcode")).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no frequent destinations", async () => {
    api.standards.list.mockResolvedValue([]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("No destinations yet.")).toBeInTheDocument());
  });

  it("lists existing frequent destinations", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.list.mockResolvedValue([
      {
        id: 1,
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
        enabled: 1,
      },
    ]);
    renderAdmin();
    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText(/Monday · 08:30 · Paddington/)).toBeInTheDocument();
  });

  it("opens the new-destination form, searches a station, and submits", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.searchStations.mockResolvedValue([
      { id: "910GPADTON", name: "Paddington", modes: ["national-rail", "elizabeth-line"] },
    ]);
    api.destinations.create.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No destinations yet.")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "+ New destination" }));

    await user.type(screen.getByPlaceholderText("e.g. Office, Mum & Dad's"), "Office");
    await user.type(screen.getByPlaceholderText("Search station name…"), "padd");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(screen.getByText("Paddington")).toBeInTheDocument());
    await user.click(screen.getByText("Paddington"));

    await user.click(screen.getByRole("button", { name: "Add destination" }));

    await waitFor(() =>
      expect(api.destinations.create).toHaveBeenCalledWith({
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
      })
    );
  });

  it("opens the new-destination form, switches to postcode, and submits", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.create.mockResolvedValue({ id: 1 });
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No destinations yet.")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "+ New destination" }));

    await user.type(screen.getByPlaceholderText("e.g. Office, Mum & Dad's"), "Zappi");
    await user.click(screen.getByRole("radio", { name: "Postcode" }));
    await user.type(screen.getByPlaceholderText("e.g. NW1 7JN"), "NW1 7JN");

    await user.click(screen.getByRole("button", { name: "Add destination" }));

    await waitFor(() =>
      expect(api.destinations.create).toHaveBeenCalledWith({
        name: "Zappi",
        destination_type: "postcode",
        tfl_identifier: "NW1 7JN",
        station_name: "NW1 7JN",
        day_of_week: 0,
        time: "08:30",
      })
    );
  });

  it("shows a backfill progress bar for a destination whose backfill is running, and hides it once done", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.list.mockResolvedValue([
      {
        id: 1,
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
        enabled: 1,
      },
    ]);
    api.destinations.backfillStatus
      .mockResolvedValueOnce({ status: "running", done: 3, total: 10 })
      .mockResolvedValueOnce({ status: "done", done: 10, total: 10 });

    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderAdmin();

    await waitFor(() => expect(screen.getByText(/Backfilling journeys… 30% \(3\/10\)/)).toBeInTheDocument());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await waitFor(() => expect(screen.queryByText(/Backfilling journeys/)).not.toBeInTheDocument());

    vi.useRealTimers();
  });

  it("shows a queued message for a destination whose backfill is waiting behind another one", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.list.mockResolvedValue([
      {
        id: 1,
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
        enabled: 1,
      },
    ]);
    api.destinations.backfillStatus
      .mockResolvedValueOnce({ status: "queued", done: 0, total: 10 })
      .mockResolvedValueOnce({ status: "running", done: 1, total: 10 });

    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderAdmin();

    await waitFor(() =>
      expect(
        screen.getByText("Queued — waiting for another destination's backfill to finish…")
      ).toBeInTheDocument()
    );
    expect(screen.queryByText(/Backfilling journeys/)).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await waitFor(() => expect(screen.getByText(/Backfilling journeys… 10% \(1\/10\)/)).toBeInTheDocument());

    vi.useRealTimers();
  });

  it("cancels the new-destination form without submitting", async () => {
    api.standards.list.mockResolvedValue([]);
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByText("No destinations yet.")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "+ New destination" }));
    expect(screen.getByPlaceholderText("e.g. Office, Mum & Dad's")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByPlaceholderText("e.g. Office, Mum & Dad's")).not.toBeInTheDocument();
    expect(api.destinations.create).not.toHaveBeenCalled();
  });

  it("deletes a frequent destination", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.list.mockResolvedValue([
      {
        id: 1,
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
        enabled: 1,
      },
    ]);
    api.destinations.remove.mockResolvedValue(null);
    const user = userEvent.setup();
    renderAdmin();

    await waitFor(() => expect(screen.getByLabelText("Delete destination")).toBeInTheDocument());
    await user.click(screen.getByLabelText("Delete destination"));

    await waitFor(() => expect(api.destinations.remove).toHaveBeenCalledWith(1));
  });

  it("switches the visible panel via the sidebar nav without unmounting the destination poller", async () => {
    api.standards.list.mockResolvedValue([]);
    api.destinations.list.mockResolvedValue([
      {
        id: 1,
        name: "Office",
        destination_type: "station",
        tfl_identifier: "910GPADTON",
        station_name: "Paddington",
        day_of_week: 0,
        time: "08:30",
        enabled: 1,
      },
    ]);
    api.destinations.backfillStatus
      .mockResolvedValueOnce({ status: "running", done: 3, total: 10 })
      .mockResolvedValueOnce({ status: "running", done: 6, total: 10 });

    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderAdmin();

    await waitFor(() => expect(screen.getByText(/Backfilling journeys… 30% \(3\/10\)/)).toBeInTheDocument());

    await gotoPanel(user, "Council tax rates");
    await waitFor(() => expect(screen.getByText("No councils yet — add a listing to get started.")).toBeInTheDocument());

    // The poller kicked off before the nav switch is still running -- its
    // setTimeout should still fire and update state even though the
    // destinations panel is no longer the visible one.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await gotoPanel(user, "Frequent destinations");
    await waitFor(() => expect(screen.getByText(/Backfilling journeys… 60% \(6\/10\)/)).toBeInTheDocument());

    vi.useRealTimers();
  });
});

describe("AdminPage council tax rates", () => {
  it("shows an empty state when there are no councils", async () => {
    api.standards.list.mockResolvedValue([]);
    renderAdmin();
    const user = userEvent.setup();
    await gotoPanel(user, "Council tax rates");
    await waitFor(() =>
      expect(screen.getByText("No councils yet — add a listing to get started.")).toBeInTheDocument()
    );
  });

  it("shows a needs-rates chip and nav dot for a council with any unset band", async () => {
    api.standards.list.mockResolvedValue([]);
    api.councilTax.list.mockResolvedValue([
      {
        gss_code: "E00000001",
        council_name: "Sampleton",
        band_a: null,
        band_b: null,
        band_c: null,
        band_d: null,
        band_e: null,
        band_f: null,
        band_g: null,
        band_h: null,
      },
    ]);
    const user = userEvent.setup();
    renderAdmin();
    await gotoPanel(user, "Council tax rates");

    await waitFor(() => expect(screen.getByText("Sampleton")).toBeInTheDocument());
    expect(screen.getByText("New — needs rates")).toBeInTheDocument();
    expect(screen.getByText("Needs rates")).toBeInTheDocument();
    expect(screen.getByTitle("1 council needs rates")).toBeInTheDocument();
  });

  it("expands a council row and submits a full-replacement rate update", async () => {
    api.standards.list.mockResolvedValue([]);
    api.councilTax.list.mockResolvedValue([
      {
        gss_code: "E00000001",
        council_name: "Sampleton",
        band_a: null,
        band_b: null,
        band_c: null,
        band_d: 2340,
        band_e: null,
        band_f: null,
        band_g: null,
        band_h: null,
      },
    ]);
    api.councilTax.update.mockResolvedValue({});
    const user = userEvent.setup();
    renderAdmin();
    await gotoPanel(user, "Council tax rates");

    await waitFor(() => expect(screen.getByText("Sampleton")).toBeInTheDocument());
    await user.click(screen.getByText("Sampleton"));

    const bandAInput = screen.getByLabelText(/Band A/);
    await user.type(bandAInput, "1200");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.councilTax.update).toHaveBeenCalledWith("E00000001", {
        council_name: "Sampleton",
        band_a: 1200,
        band_b: null,
        band_c: null,
        band_d: 2340,
        band_e: null,
        band_f: null,
        band_g: null,
        band_h: null,
      })
    );
  });

  it("clears a council's rates", async () => {
    api.standards.list.mockResolvedValue([]);
    api.councilTax.list.mockResolvedValue([
      {
        gss_code: "E00000001",
        council_name: "Sampleton",
        band_a: 1000,
        band_b: null,
        band_c: null,
        band_d: null,
        band_e: null,
        band_f: null,
        band_g: null,
        band_h: null,
      },
    ]);
    api.councilTax.remove.mockResolvedValue(null);
    const user = userEvent.setup();
    renderAdmin();
    await gotoPanel(user, "Council tax rates");

    await waitFor(() => expect(screen.getByText("Sampleton")).toBeInTheDocument());
    await user.click(screen.getByText("Sampleton"));
    await user.click(screen.getByRole("button", { name: "Clear rates" }));

    await waitFor(() => expect(api.councilTax.remove).toHaveBeenCalledWith("E00000001"));
  });
});
