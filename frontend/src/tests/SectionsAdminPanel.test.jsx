import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import SectionsAdminPanel from "../components/SectionsAdminPanel.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    detailSections: {
      get: vi.fn(),
      put: vi.fn(),
    },
  },
}));

const CONFIG = {
  details_expanded: true,
  description_features_expanded: true,
  nearest_stations_expanded: true,
  floorplans_expanded: true,
  epc_expanded: false,
  room_sizes_expanded: false,
  commute_expanded: true,
  frequent_destinations_expanded: true,
  mortgage_expanded: true,
  crime_expanded: false,
  jobs_expanded: false,
};

describe("SectionsAdminPanel", () => {
  it("renders nothing and doesn't fetch when inactive", () => {
    const { container } = render(<SectionsAdminPanel active={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.detailSections.get).not.toHaveBeenCalled();
  });

  it("loads current config into checkboxes once active", async () => {
    api.detailSections.get.mockResolvedValue(CONFIG);
    render(<SectionsAdminPanel active={true} />);

    await waitFor(() => expect(api.detailSections.get).toHaveBeenCalled());
    await screen.findByText("Details");
    // Find each row specifically via its label text.
    const epcRow = screen.getByText("EPC").closest("li");
    expect(epcRow.querySelector("input[type=checkbox]").checked).toBe(false);
    const commuteRow = screen.getByText("Commute").closest("li");
    expect(commuteRow.querySelector("input[type=checkbox]").checked).toBe(true);
  });

  it("Save PUTs all 11 values", async () => {
    const user = userEvent.setup();
    api.detailSections.get.mockResolvedValue(CONFIG);
    api.detailSections.put.mockResolvedValue(CONFIG);
    render(<SectionsAdminPanel active={true} />);

    await waitFor(() => expect(api.detailSections.get).toHaveBeenCalled());
    await screen.findByText("Details");

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.detailSections.put).toHaveBeenCalledWith(CONFIG));
  });
});
