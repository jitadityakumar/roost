import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import FieldColorsAdminPanel from "../components/FieldColorsAdminPanel.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    fieldColors: {
      list: vi.fn(),
      put: vi.fn(),
      remove: vi.fn(),
    },
  },
}));

const THRESHOLDS = [
  { field: "floor_area_sqft", green_cutoff: "950", red_cutoff: "750", higher_is_better: 1 },
  { field: "epc_current", green_cutoff: "C", red_cutoff: "E", higher_is_better: null },
];

describe("FieldColorsAdminPanel", () => {
  it("renders nothing and doesn't fetch when inactive", () => {
    const { container } = render(<FieldColorsAdminPanel active={false} />);
    expect(container).toBeEmptyDOMElement();
    expect(api.fieldColors.list).not.toHaveBeenCalled();
  });

  it("loads stored thresholds into their field's row", async () => {
    api.fieldColors.list.mockResolvedValue(THRESHOLDS);
    render(<FieldColorsAdminPanel active={true} />);

    await waitFor(() => expect(api.fieldColors.list).toHaveBeenCalled());
    await screen.findByText("Floor area (sq ft)");

    const floorAreaCard = screen.getByText("Floor area (sq ft)").closest(".rule-card");
    expect(floorAreaCard.querySelector("input").value).toBe("950");
    expect(floorAreaCard.querySelector(".direction-toggle button.active").textContent).toBe("Higher = better");

    const epcCard = screen.getByText("EPC current").closest(".rule-card");
    expect(epcCard.querySelectorAll("select")[0].value).toBe("C");
  });

  it("shows a blank row for a field with no stored threshold", async () => {
    api.fieldColors.list.mockResolvedValue(THRESHOLDS);
    render(<FieldColorsAdminPanel active={true} />);

    await screen.findByText("Price");
    const priceCard = screen.getByText("Price").closest(".rule-card");
    priceCard.querySelectorAll("input").forEach((input) => expect(input.value).toBe(""));
  });

  it("Save PUTs a field with a cutoff set and clears a field left blank", async () => {
    const user = userEvent.setup();
    api.fieldColors.list.mockResolvedValue([]);
    api.fieldColors.put.mockResolvedValue({});
    api.fieldColors.remove.mockResolvedValue(null);
    render(<FieldColorsAdminPanel active={true} />);

    await screen.findByText("Price");
    const priceCard = screen.getByText("Price").closest(".rule-card");
    const [greenInput] = priceCard.querySelectorAll("input");
    await user.type(greenInput, "600000");

    api.fieldColors.list.mockResolvedValue([
      { field: "price_gbp", green_cutoff: "600000", red_cutoff: null, higher_is_better: 0 },
    ]);
    await user.click(screen.getByRole("button", { name: "Save thresholds" }));

    await waitFor(() =>
      expect(api.fieldColors.put).toHaveBeenCalledWith(
        "price_gbp",
        expect.objectContaining({ green_cutoff: "600000" })
      )
    );
    // Every other field had no cutoffs entered -- cleared, not upserted.
    expect(api.fieldColors.remove).toHaveBeenCalledWith("lease_years_remaining");
    expect(api.fieldColors.put).not.toHaveBeenCalledWith("lease_years_remaining", expect.anything());
  });

  it("toggling direction flips the higher/lower label on the threshold rows", async () => {
    const user = userEvent.setup();
    api.fieldColors.list.mockResolvedValue([]);
    render(<FieldColorsAdminPanel active={true} />);

    await screen.findByText("Price");
    const priceCard = screen.getByText("Price").closest(".rule-card");
    // Blank rows default to higher_is_better: true.
    expect(priceCard.textContent).toContain("Green at/above");

    const toggleButtons = priceCard.querySelectorAll(".direction-toggle button");
    await user.click(toggleButtons[0]); // "Lower = better", scoped to Price's own card
    expect(priceCard.textContent).toContain("Green at/below");
  });
});
