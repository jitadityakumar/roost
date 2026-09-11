import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FloorplanBaselineTracePage from "../components/FloorplanBaselineTracePage.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    floorplan: {
      getBaseline: vi.fn(),
      putBaseline: vi.fn(),
    },
  },
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/floorplan-baseline/trace"]}>
      <Routes>
        <Route path="/admin/floorplan-baseline/trace" element={<FloorplanBaselineTracePage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("FloorplanBaselineTracePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("prompts to set an image when no baseline image exists yet, in the full-width tracer-page shell", async () => {
    api.floorplan.getBaseline.mockResolvedValue({
      id: 1, image_blob: null, image_w: null, image_h: null, active_scale: null, rooms: [], shapes: [],
    });
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("Set a baseline image to start tracing.")).toBeInTheDocument());
    expect(screen.getByText("Set baseline image…")).toBeInTheDocument();
    expect(container.querySelector(".tracer-page")).toBeInTheDocument();
  });

  it("renders the tracer once a baseline image is already set", async () => {
    api.floorplan.getBaseline.mockResolvedValue({
      id: 1, image_blob: "data:image/png;base64,abc", image_w: 100, image_h: 100, active_scale: 10, rooms: [], shapes: [],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("Change baseline image…")).toBeInTheDocument());
  });

  it("prefills the internal sq ft input from the loaded baseline", async () => {
    api.floorplan.getBaseline.mockResolvedValue({
      id: 1, image_blob: "data:image/png;base64,abc", image_w: 100, image_h: 100, active_scale: 10,
      internal_sqft: 850, rooms: [], shapes: [],
    });
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("850")).toBeInTheDocument());
  });

  it("leaves the internal sq ft input blank when the baseline has none set yet", async () => {
    api.floorplan.getBaseline.mockResolvedValue({
      id: 1, image_blob: "data:image/png;base64,abc", image_w: 100, image_h: 100, active_scale: 10,
      internal_sqft: null, rooms: [], shapes: [],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("Change baseline image…")).toBeInTheDocument());
    expect(screen.getByPlaceholderText("e.g. 850")).toHaveValue(null);
  });

  it("includes the edited internal sq ft in the save payload", async () => {
    api.floorplan.getBaseline.mockResolvedValue({
      id: 1, image_blob: "data:image/png;base64,abc", image_w: 100, image_h: 100, active_scale: 10,
      internal_sqft: null, rooms: [], shapes: [],
    });
    api.floorplan.putBaseline.mockResolvedValue({
      id: 1, image_blob: "data:image/png;base64,abc", image_w: 100, image_h: 100, active_scale: 10,
      internal_sqft: 900, rooms: [], shapes: [],
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByPlaceholderText("e.g. 850")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("e.g. 850"), "900");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.floorplan.putBaseline).toHaveBeenCalled());
    expect(api.floorplan.putBaseline.mock.calls[0][0].internal_sqft).toBe(900);
  });
});
