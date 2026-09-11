import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import FloorplanTracePage from "../components/FloorplanTracePage.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    mediaList: vi.fn(),
    mediaUrl: (id, category, filename) => `/media/${id}/${category}/${filename}`,
    floorplan: {
      getListingTrace: vi.fn(),
      putListingTrace: vi.fn(),
    },
  },
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/listings/1/trace"]}>
      <Routes>
        <Route path="/listings/:id/trace" element={<FloorplanTracePage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("FloorplanTracePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("shows an error state when the listing has no floor plan image", async () => {
    api.mediaList.mockResolvedValue({ photos: [], floorplans: [], epc: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText("This listing has no floor plan image to trace.")).toBeInTheDocument());
  });

  it("auto-selects the single floor plan image and loads its trace", async () => {
    api.mediaList.mockResolvedValue({ photos: [], floorplans: ["01.jpeg"], epc: [] });
    api.floorplan.getListingTrace.mockResolvedValue({ rooms: [], shapes: [], active_scale: 12 });
    renderPage();
    await waitFor(() => expect(api.floorplan.getListingTrace).toHaveBeenCalledWith("1", "01.jpeg"));
    await waitFor(() => expect(screen.getByText("Trace room sizes")).toBeInTheDocument());
  });

  it("prompts to pick an image when the listing has more than one floor plan", async () => {
    api.mediaList.mockResolvedValue({ photos: [], floorplans: ["01.jpeg", "02.jpeg"], epc: [] });
    api.floorplan.getListingTrace.mockResolvedValue({ rooms: [], shapes: [], active_scale: null });
    renderPage();
    await waitFor(() => expect(screen.getByText("Which floor plan image?")).toBeInTheDocument());
    expect(api.floorplan.getListingTrace).not.toHaveBeenCalled();

    const user = userEvent.setup();
    await user.click(screen.getByAltText("01.jpeg"));
    await waitFor(() => expect(api.floorplan.getListingTrace).toHaveBeenCalledWith("1", "01.jpeg"));
  });

  it("starts blank when the chosen image has no existing trace", async () => {
    api.mediaList.mockResolvedValue({ photos: [], floorplans: ["01.jpeg"], epc: [] });
    api.floorplan.getListingTrace.mockRejectedValue(new Error("404"));
    renderPage();
    await waitFor(() => expect(screen.getByText("Trace room sizes")).toBeInTheDocument());
  });
});
