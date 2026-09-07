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
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children, center }) => (
    <div data-testid="marker" data-lat={center[0]} data-lon={center[1]}>
      {children}
    </div>
  ),
  Popup: ({ children }) => <div data-testid="popup">{children}</div>,
  useMap: () => ({ fitBounds: vi.fn() }),
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
    expect(screen.getByText("1 of 2 listings shown")).toBeInTheDocument();
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

  it("excludes listings with no coordinates from both the count and the map", async () => {
    api.list.mockResolvedValue([
      makeListing({ id: 1, user_status: "triage", latitude: null, longitude: null }),
      makeListing({ id: 2, user_status: "triage" }),
    ]);
    renderMap();

    await waitFor(() => expect(screen.getAllByTestId("marker")).toHaveLength(1));
    expect(screen.getByText("1 of 1 listings shown")).toBeInTheDocument();
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
    expect(screen.getByText("0 of 5 listings shown")).toBeInTheDocument();
  });

  it("shows a fetch error", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    renderMap();
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
