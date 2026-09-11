import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
});
