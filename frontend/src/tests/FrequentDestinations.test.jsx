import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import FrequentDestinations from "../components/FrequentDestinations.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { listingDestinations: vi.fn(), refreshListingDestinations: vi.fn() },
}));

describe("FrequentDestinations", () => {
  it("shows a waiting message when the listing isn't ready yet", () => {
    render(<FrequentDestinations listingId={1} ready={false} />);
    expect(screen.getByText(/Waiting for listing details/)).toBeInTheDocument();
    expect(api.listingDestinations).not.toHaveBeenCalled();
  });

  it("shows an empty state when no destinations are configured", async () => {
    api.listingDestinations.mockResolvedValue([]);
    render(<FrequentDestinations listingId={1} ready={true} />);
    await waitFor(() =>
      expect(screen.getByText(/No frequent destinations configured/)).toBeInTheDocument()
    );
  });

  it("renders a resolved direct destination with duration, route, and planner link", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        crs: "PAD",
        resolved: true,
        duration_minutes: 24,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "WOK",
        origin_name: "Woking",
        interchange_crs: null,
        departure_time: "08:40:00",
        arrival_time: "09:04:00",
        planner_url: "http://planner.example/results?from_=WOK&to=PAD",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("24m")).toBeInTheDocument();
    expect(screen.getByText("· WOK → PAD")).toBeInTheDocument();
    expect(screen.getByText("direct")).toBeInTheDocument();
    expect(screen.queryByText(/South Western Railway/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View on Train Journey Planner/ })).toHaveAttribute(
      "href",
      "http://planner.example/results?from_=WOK&to=PAD"
    );
  });

  it("renders an interchange destination's change station instead of the operator", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Bandol",
        day_of_week: 6,
        day_label: "Sunday",
        time: "12:00",
        station_name: "London Road (Guildford)",
        crs: "LRD",
        resolved: true,
        duration_minutes: 45,
        kind: "interchange",
        num_changes: 1,
        operator: "South Western Railway",
        origin_crs: "SUR",
        origin_name: "Surbiton",
        interchange_crs: "CLJ",
        departure_time: "12:05:00",
        arrival_time: "12:50:00",
        planner_url: "http://planner.example/results?from_=SUR&to=LRD",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Bandol")).toBeInTheDocument());
    expect(screen.getByText("· SUR → LRD")).toBeInTheDocument();
    expect(screen.getByText("1 change (via CLJ)")).toBeInTheDocument();
    expect(screen.queryByText(/South Western Railway/)).not.toBeInTheDocument();
  });

  it("formats durations over an hour as 1h21m", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Airport",
        day_of_week: 5,
        day_label: "Saturday",
        time: "06:00",
        station_name: "Gatwick Airport",
        resolved: true,
        duration_minutes: 81,
        kind: "direct",
        num_changes: 0,
        operator: "Southern",
        origin_crs: "WOK",
        origin_name: "Woking",
        departure_time: "06:10:00",
        arrival_time: "07:31:00",
        planner_url: null,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("1h21m")).toBeInTheDocument());
  });

  it("renders an unresolved destination with a manual-search fallback link", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Sister's wedding venue",
        day_of_week: 5,
        day_label: "Saturday",
        time: "23:00",
        station_name: "Somewhere",
        resolved: false,
        planner_url: null,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText(/No train route found/)).toBeInTheDocument());
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("recomputes journeys via the refresh button", async () => {
    api.listingDestinations.mockResolvedValue([]);
    api.refreshListingDestinations.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText(/No frequent destinations configured/)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Recompute journeys" }));

    await waitFor(() => expect(api.refreshListingDestinations).toHaveBeenCalledWith(1));
  });
});
