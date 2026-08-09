import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Commute from "../components/Commute.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { commute: vi.fn() },
}));

describe("Commute", () => {
  it("shows a waiting message when the listing isn't ready yet", () => {
    render(<Commute listingId={1} ready={false} />);
    expect(screen.getByText(/Waiting for listing details/)).toBeInTheDocument();
    expect(api.commute).not.toHaveBeenCalled();
  });

  it("shows a loading state then renders station termini on success", async () => {
    api.commute.mockResolvedValue({
      stations: [
        {
          name: "Woking",
          crs: "WOK",
          distance: 0.34410279879311945,
          error: null,
          termini: {
            peak: {
              termini: [
                {
                  terminus_crs: "WAT",
                  terminus_name: "London Waterloo",
                  journey_time_mins: 25,
                  journey_range: "24–28",
                  stops_range: "1–2",
                  trains_per_hour: 11,
                  operators: "SW",
                  operators_title: "South Western Railway",
                  also_calls_at: [],
                  tube_lines: [{ line: "Jubilee", color: "#A0A5A9" }],
                },
              ],
            },
            offpeak: { termini: [] },
          },
        },
      ],
    });

    render(<Commute listingId={1} ready={true} />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText(/Woking/)).toBeInTheDocument());
    expect(screen.getByText("(0.34 mi)")).toBeInTheDocument();
    expect(screen.getByText("London Waterloo")).toBeInTheDocument();
    expect(screen.getByText("25m · 11/hr · 24m-28m · 1-2 stops")).toBeInTheDocument();
    expect(screen.getByText("South Western Railway")).toBeInTheDocument();
    expect(screen.getByText("Jubilee")).toBeInTheDocument();
    expect(screen.queryByText("Off-peak")).not.toBeInTheDocument();
  });

  it("renders each terminus with its own operator, and an also-calls-at note when present", async () => {
    api.commute.mockResolvedValue({
      stations: [
        {
          name: "Denmark Hill",
          crs: "DMK",
          distance: 3.1,
          error: null,
          termini: {
            peak: {
              termini: [
                {
                  terminus_crs: "VIC",
                  terminus_name: "London Victoria",
                  journey_time_mins: 10,
                  journey_range: "10–10",
                  stops_range: "1–1",
                  trains_per_hour: 4,
                  operators_title: "Southeastern",
                  also_calls_at: [],
                  tube_lines: [],
                },
                {
                  terminus_crs: "BFR",
                  terminus_name: "London Blackfriars",
                  journey_time_mins: 12,
                  journey_range: "12–12",
                  stops_range: "2–2",
                  trains_per_hour: 4,
                  operators_title: "Thameslink",
                  also_calls_at: [{ terminus_crs: "STP", terminus_name: "London St Pancras International" }],
                  tube_lines: [],
                },
              ],
            },
            offpeak: { termini: [] },
          },
        },
      ],
    });

    render(<Commute listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText("London Victoria")).toBeInTheDocument());
    expect(screen.getByText("Southeastern")).toBeInTheDocument();
    expect(screen.getByText("Thameslink")).toBeInTheDocument();
    expect(screen.getByText(/also to London St Pancras International/)).toBeInTheDocument();
  });

  it("picks black text on a light tube-line color and white text on a dark one", async () => {
    api.commute.mockResolvedValue({
      stations: [
        {
          name: "Woking",
          crs: "WOK",
          distance: 0.3,
          error: null,
          termini: {
            peak: {
              termini: [
                {
                  terminus_crs: "WAT",
                  terminus_name: "London Waterloo",
                  journey_time_mins: 25,
                  journey_range: "24–28",
                  stops_range: "1–2",
                  trains_per_hour: 11,
                  operators_title: "South Western Railway",
                  tube_lines: [
                    { line: "Waterloo & City", color: "#95CDBA" },
                    { line: "Northern", color: "#000000" },
                  ],
                },
              ],
            },
            offpeak: { termini: [] },
          },
        },
      ],
    });

    render(<Commute listingId={1} ready={true} />);
    const lightBadge = await screen.findByText("Waterloo & City");
    expect(lightBadge).toHaveStyle({ color: "#000" });
    expect(screen.getByText("Northern")).toHaveStyle({ color: "#fff" });
  });

  it("shows an empty state when no stations resolve", async () => {
    api.commute.mockResolvedValue({ stations: [] });
    render(<Commute listingId={1} ready={true} />);
    await waitFor(() =>
      expect(screen.getByText(/No nearby National Rail stations found/)).toBeInTheDocument()
    );
  });

  it("shows a per-station error without failing the whole section", async () => {
    api.commute.mockResolvedValue({
      stations: [{ name: "Clapham Junction", crs: "CLJ", distance: 0.4, error: "boom", termini: null }],
    });
    render(<Commute listingId={1} ready={true} />);
    await waitFor(() =>
      expect(screen.getByText(/Couldn't load commute times for this station/)).toBeInTheDocument()
    );
  });

  it("shows a section-level error when the request itself fails", async () => {
    api.commute.mockRejectedValue(new Error("network down"));
    render(<Commute listingId={1} ready={true} />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
