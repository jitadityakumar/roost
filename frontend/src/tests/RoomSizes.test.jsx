import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import RoomSizes from "../components/RoomSizes.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    floorplan: {
      comparison: vi.fn(),
    },
  },
}));

function renderWith(props) {
  return render(
    <MemoryRouter>
      <RoomSizes listingId="1" ready floorplanFilenames={["01.jpeg"]} {...props} />
    </MemoryRouter>
  );
}

describe("RoomSizes", () => {
  it("renders nothing when the listing has no floor plan image", () => {
    const { container } = render(
      <MemoryRouter>
        <RoomSizes listingId="1" ready floorplanFilenames={[]} />
      </MemoryRouter>
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while extraction isn't done yet", () => {
    const { container } = render(
      <MemoryRouter>
        <RoomSizes listingId="1" ready={false} floorplanFilenames={["01.jpeg"]} />
      </MemoryRouter>
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows "Add trace" when there is no trace yet', async () => {
    const notFound = new Error("no trace with shapes for this listing yet");
    notFound.status = 404;
    api.floorplan.comparison.mockRejectedValue(notFound);
    renderWith();
    await waitFor(() => expect(screen.getByText("Add trace")).toBeInTheDocument());
  });

  it("fails soft when there's no baseline yet", async () => {
    api.floorplan.comparison.mockResolvedValue({ baseline_has_shapes: false, summary: {}, types: [] });
    renderWith();
    await waitFor(() =>
      expect(screen.getByText("Trace a baseline floor plan in Admin to compare room sizes.")).toBeInTheDocument()
    );
  });

  it("renders the comparison and an Edit trace button once both baseline and listing are traced", async () => {
    api.floorplan.comparison.mockResolvedValue({
      baseline_has_shapes: true,
      summary: {
        indoor: { baseline: 10, listing: 10, delta_pct: 0 },
        outdoor: { baseline: 0, listing: 0, delta_pct: null },
        grand: { baseline: 10, listing: 10, delta_pct: 0 },
        floor_area_cross_check: null,
      },
      types: [],
    });
    renderWith();
    await waitFor(() => expect(screen.getByText("Edit trace")).toBeInTheDocument());
    expect(screen.getByText("Indoor total")).toBeInTheDocument();
  });

  it("shows a real error distinctly from the no-trace state", async () => {
    api.floorplan.comparison.mockRejectedValue(new Error("500 Internal Server Error"));
    renderWith();
    await waitFor(() => expect(screen.getByText(/Couldn't load room sizes/)).toBeInTheDocument());
    expect(screen.queryByText("Add trace")).not.toBeInTheDocument();
  });
});
