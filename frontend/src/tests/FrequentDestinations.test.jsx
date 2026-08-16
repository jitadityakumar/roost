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

  it("renders a resolved direct destination with duration and station names", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        destination_type: "station",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        resolved: true,
        duration_minutes: 24,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Paddington",
        interchange_crs: null,
        departure_time: "2026-08-17T08:40:00",
        arrival_time: "2026-08-17T09:04:00",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("24m")).toBeInTheDocument();
    expect(screen.getByText("Woking → Paddington")).toBeInTheDocument();
    expect(screen.getByText("· Mon 08:30")).toBeInTheDocument();
    expect(screen.getByText("direct")).toBeInTheDocument();
    expect(screen.queryByText(/South Western Railway/)).not.toBeInTheDocument();
  });

  it("renders an interchange destination's change count without a via suffix", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Bandol",
        destination_type: "postcode",
        day_of_week: 6,
        day_label: "Sunday",
        time: "12:00",
        station_name: "GU5 0AB",
        resolved: true,
        duration_minutes: 45,
        kind: "interchange",
        num_changes: 1,
        operator: "South Western Railway",
        origin_crs: "910GSURBIT",
        origin_name: "Surbiton",
        arrival_name: "London Road (Guildford)",
        interchange_crs: "910GCLPHMJ",
        departure_time: "2026-08-17T12:05:00",
        arrival_time: "2026-08-17T12:50:00",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Bandol")).toBeInTheDocument());
    expect(screen.getByText("Surbiton → London Road (Guildford)")).toBeInTheDocument();
    expect(screen.getByText("· Sun 12:00")).toBeInTheDocument();
    expect(screen.getByText("1 change")).toBeInTheDocument();
    expect(screen.queryByText(/via/)).not.toBeInTheDocument();
    expect(screen.queryByText(/South Western Railway/)).not.toBeInTheDocument();
  });

  it("renders the home duration diff as a superscript next to the duration", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        destination_type: "station",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        resolved: true,
        duration_minutes: 42,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Paddington",
        interchange_crs: null,
        departure_time: "2026-08-17T08:40:00",
        arrival_time: "2026-08-17T09:04:00",
        home_duration_diff_minutes: 24,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("(+24)")).toBeInTheDocument();
  });

  it("renders a negative home duration diff without a leading plus", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        destination_type: "station",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        resolved: true,
        duration_minutes: 42,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Paddington",
        interchange_crs: null,
        departure_time: "2026-08-17T08:40:00",
        arrival_time: "2026-08-17T09:04:00",
        home_duration_diff_minutes: -10,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("(-10)")).toBeInTheDocument();
  });

  it("renders a zero home duration diff with a leading plus", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        destination_type: "station",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        resolved: true,
        duration_minutes: 42,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Paddington",
        interchange_crs: null,
        departure_time: "2026-08-17T08:40:00",
        arrival_time: "2026-08-17T09:04:00",
        home_duration_diff_minutes: 0,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("(+0)")).toBeInTheDocument();
  });

  it("omits the home diff superscript when not provided", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Office",
        destination_type: "station",
        day_of_week: 0,
        day_label: "Monday",
        time: "08:30",
        station_name: "Paddington",
        resolved: true,
        duration_minutes: 24,
        kind: "direct",
        num_changes: 0,
        operator: "South Western Railway",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Paddington",
        interchange_crs: null,
        departure_time: "2026-08-17T08:40:00",
        arrival_time: "2026-08-17T09:04:00",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("24m")).toBeInTheDocument());
    expect(document.querySelector(".destination-home-diff")).not.toBeInTheDocument();
  });

  it("formats durations over an hour as 1h21m", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Airport",
        destination_type: "station",
        day_of_week: 5,
        day_label: "Saturday",
        time: "06:00",
        station_name: "Gatwick Airport",
        resolved: true,
        duration_minutes: 81,
        kind: "direct",
        num_changes: 0,
        operator: "Southern",
        origin_crs: "910GWOKING",
        origin_name: "Woking",
        arrival_name: "Gatwick Airport",
        departure_time: "2026-08-17T06:10:00",
        arrival_time: "2026-08-17T07:31:00",
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("1h21m")).toBeInTheDocument());
  });

  it("renders an unresolved destination with plain no-journey-found copy", async () => {
    api.listingDestinations.mockResolvedValue([
      {
        destination_id: 1,
        name: "Sister's wedding venue",
        destination_type: "postcode",
        day_of_week: 5,
        day_label: "Saturday",
        time: "23:00",
        station_name: "SW1A 1AA",
        resolved: false,
      },
    ]);
    render(<FrequentDestinations listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText(/No journey found/)).toBeInTheDocument());
    expect(screen.getByText(/SW1A 1AA/)).toBeInTheDocument();
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
