import { render, screen, waitFor } from "@testing-library/react";
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
});

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
});
