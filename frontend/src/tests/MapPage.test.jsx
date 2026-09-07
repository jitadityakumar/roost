import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import MapPage from "../components/MapPage.jsx";

vi.mock("../api.js", () => ({
  api: {
    list: vi.fn(),
    mediaList: vi.fn().mockResolvedValue({ photos: [] }),
    mediaUrl: (id, category, filename) => `/media/${id}/${category}/${filename}`,
  },
}));

// react-leaflet's MapContainer needs real layout (getBoundingClientRect etc.)
// that jsdom doesn't provide -- stub the map primitives so the page's own
// data-fetch/filter logic can be tested without a real Leaflet map.
const fitBounds = vi.fn();
const setView = vi.fn();
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children, center, pathOptions }) => (
    <div data-testid="marker" data-lat={center[0]} data-lon={center[1]} data-color={pathOptions.color}>
      {children}
    </div>
  ),
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
  useMap: () => ({ fitBounds, setView }),
}));

import { api } from "../api.js";

function makeListing(overrides = {}) {
  return {
    id: 1,
    extraction_status: "done",
    pipeline_status: null,
    user_status: "triage",
    price_gbp: 500000,
    address: "1 Test Street",
    bedrooms: 2,
    bathrooms: 1,
    property_type: "Flat",
    latitude: 51.5,
    longitude: -0.1,
    ...overrides,
  };
}

function renderMap() {
  return render(
    <MemoryRouter>
      <MapPage />
    </MemoryRouter>
  );
}

describe("MapPage", () => {
  it("shows only triage listings by default", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage" }),
      makeListing({ id: 2, user_status: "approved" }),
    ]);
    renderMap();

    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(1));
    // Denominator is listings matching the *selected* statuses (triage only,
    // by default), not every plottable listing regardless of status.
    expect(screen.getByText("1 of 1 listings shown")).toBeInTheDocument();
  });

  it("supports toggling multiple statuses on at once", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage" }),
      makeListing({ id: 2, user_status: "approved" }),
      makeListing({ id: 3, user_status: "rejected" }),
    ]);
    renderMap();
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: /approved/i }));
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(2));

    fireEvent.click(screen.getByRole("button", { name: /rejected/i }));
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(3));

    // toggling triage back off leaves the other two selected
    fireEvent.click(screen.getByRole("button", { name: /^triage$/i }));
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(2));
  });

  it("excludes listings with no coordinates from the map but still surfaces them in the count", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage", latitude: null, longitude: null }),
      makeListing({ id: 2, user_status: "triage" }),
    ]);
    renderMap();

    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(1));
    // 2 triage listings match the filter, but only 1 has coordinates to plot
    // -- the gap must stay visible rather than silently shrinking the total.
    expect(screen.getByText("1 of 2 listings shown (1 without map coordinates)")).toBeInTheDocument();
  });

  it("select all / clear all toggles every status at once", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage" }),
      makeListing({ id: 2, user_status: "approved" }),
      makeListing({ id: 3, user_status: "rejected" }),
      makeListing({ id: 4, user_status: "viewing" }),
      makeListing({ id: 5, user_status: "contacted" }),
    ]);
    renderMap();
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: /select all/i }));
    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(5));

    fireEvent.click(screen.getByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(screen.queryAllByTestId("marker")).toHaveLength(0));
    // No status selected -- nothing matches the filter, so the denominator
    // is 0 too (not the grand total across every status).
    expect(screen.getByText("0 of 0 listings shown")).toBeInTheDocument();
  });

  it("shows a fetch error", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    renderMap();
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });

  it("colors each marker per its status, distinctly", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage" }),
      makeListing({ id: 2, user_status: "rejected" }),
    ]);
    renderMap();
    fireEvent.click(screen.getByRole("button", { name: /rejected/i }));

    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(2));
    const colors = screen.getAllByTestId("marker").map((el) => el.dataset.color);
    expect(colors[0]).toBeTruthy();
    expect(colors[1]).toBeTruthy();
    expect(colors[0]).not.toBe(colors[1]);
  });

  it("re-frames the map to fit the visible pins, and resets to the default view once the filter is cleared", async () => {
    api.list.mockResolvedValue([makeListing({ id: 1, user_status: "triage" })]);
    renderMap();

    await waitFor(() => expect(fitBounds).toHaveBeenCalledWith([[51.5, -0.1]], expect.any(Object)));

    fireEvent.click(screen.getByRole("button", { name: /^triage$/i }));
    await waitFor(() => expect(setView).toHaveBeenCalled());
  });

  it("falls back to the placeholder thumbnail when the resolved photo fails to load", async () => {
    api.mediaList.mockResolvedValue({ photos: ["01.jpeg"] });
    api.list.mockResolvedValue([makeListing({ id: 1, user_status: "triage" })]);
    renderMap();

    const img = await screen.findByRole("img", { name: /photo of/i });
    fireEvent.error(img);

    await waitFor(() => expect(screen.queryByRole("img", { name: /photo of/i })).not.toBeInTheDocument());
    expect(document.querySelector(".map-popup-thumb-placeholder")).toBeInTheDocument();
  });
});
