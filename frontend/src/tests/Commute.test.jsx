import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Commute, { mergeTermini } from "../components/Commute.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { commute: vi.fn() },
}));

// Deterministic regardless of whether the gitignored logo files exist.
vi.mock("../components/networkLogos.js", () => ({
  logoUrlForType: () => undefined,
  walkingLogoUrl: () => undefined,
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
    expect(screen.getByText("No off-peak")).toBeInTheDocument();
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
    expect(screen.getByText("also to STP")).toBeInTheDocument();
    expect(screen.queryByText(/London St Pancras International/)).not.toBeInTheDocument();
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

  it("uses the API's line colour for a line missing from the badge table", async () => {
    api.commute.mockResolvedValue({
      stations: [
        {
          name: "Woking", crs: "WOK", distance: 0.3, error: null,
          termini: {
            peak: {
              termini: [
                {
                  terminus_crs: "WAT", terminus_name: "London Waterloo", journey_time_mins: 25,
                  journey_range: "24–28", stops_range: "1–2", trains_per_hour: 11,
                  operators_title: "",
                  tube_lines: [{ line: "Brand New Line", color: "#ABCDEF" }],
                },
              ],
            },
            offpeak: { termini: [] },
          },
        },
      ],
    });
    render(<Commute listingId={1} ready={true} />);
    expect(await screen.findByText("Brand New Line")).toHaveStyle({ backgroundColor: "#ABCDEF" });
  });

  it("renders operators as badges, splitting a combined operators_title", async () => {
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
                  operators_title: "South Western Railway, Unknown Trains",
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
    expect(await screen.findByText("South Western Railway")).toHaveStyle({
      backgroundColor: "#24398C",
    });
    expect(screen.getByRole("img", { name: "South Western Railway" })).toHaveTextContent("SW");
    // unknown operator falls back to a neutral tile rather than vanishing
    expect(screen.getByText("Unknown Trains")).toBeInTheDocument();
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

  function stationWithWalk(overrides) {
    return {
      name: "Clapham Junction",
      crs: "CLJ",
      distance: 0.4,
      error: null,
      termini: null,
      walk_distance_meters: null,
      walk_duration_seconds: null,
      walk_maps_url: null,
      ...overrides,
    };
  }

  it("shows the computed walk distance/duration together as one maps link, colored green for a short walk", async () => {
    api.commute.mockResolvedValue({
      stations: [
        stationWithWalk({
          walk_distance_meters: 500,
          walk_duration_seconds: 360,
          walk_maps_url: "https://www.google.com/maps/dir/?api=1&travelmode=walking",
        }),
      ],
    });
    render(<Commute listingId={1} ready={true} />);

    const link = await screen.findByRole("link", { name: /500m · 6 min walk/ });
    expect(link).toHaveAttribute("href", "https://www.google.com/maps/dir/?api=1&travelmode=walking");
    expect(link).toHaveClass("station-walk-duration-good");
    expect(screen.queryByText("(0.31 mi)")).not.toBeInTheDocument();
  });

  it("switches from meters to one-decimal km above 1000m", async () => {
    api.commute.mockResolvedValue({
      stations: [
        stationWithWalk({ walk_distance_meters: 1250, walk_duration_seconds: 900, walk_maps_url: "https://maps/x" }),
      ],
    });
    render(<Commute listingId={1} ready={true} />);
    await screen.findByRole("link", { name: /1\.3km · 15 min walk/ });
  });

  it("colors a medium walk amber and a long walk red", async () => {
    api.commute.mockResolvedValue({
      stations: [
        stationWithWalk({
          crs: "A",
          walk_distance_meters: 1200,
          walk_duration_seconds: 15 * 60,
          walk_maps_url: "https://maps/a",
        }),
        stationWithWalk({
          crs: "B",
          name: "Woking",
          walk_distance_meters: 2000,
          walk_duration_seconds: 25 * 60,
          walk_maps_url: "https://maps/b",
        }),
      ],
    });
    render(<Commute listingId={1} ready={true} />);

    const amber = await screen.findByRole("link", { name: /15 min walk/ });
    expect(amber).toHaveClass("station-walk-duration-warn");
    const red = screen.getByRole("link", { name: /25 min walk/ });
    expect(red).toHaveClass("station-walk-duration-bad");
  });

  it("falls back to Rightmove's raw distance and plain text (no link) when no walk data is stored", async () => {
    api.commute.mockResolvedValue({ stations: [stationWithWalk({})] });
    render(<Commute listingId={1} ready={true} />);

    await waitFor(() => expect(screen.getByText(/Clapham Junction/)).toBeInTheDocument());
    expect(screen.getByText("(0.40 mi)")).toBeInTheDocument();
    expect(screen.queryByText(/min walk/)).not.toBeInTheDocument();
  });
});

const T = (crs, name, extra = {}) => ({
  terminus_crs: crs,
  terminus_name: name,
  journey_time_mins: 20,
  journey_range: "19–21",
  stops_range: "1–2",
  trains_per_hour: 4,
  operators_title: "Southern",
  tube_lines: [],
  ...extra,
});

describe("mergeTermini", () => {
  it("pairs by terminus code, follows peak order, and appends off-peak-only termini", () => {
    const rows = mergeTermini({
      peak: { termini: [T("VIC", "London Victoria"), T("LBG", "London Bridge")] },
      offpeak: { termini: [T("LBG", "London Bridge"), T("VIC", "London Victoria"), T("BFR", "London Blackfriars")] },
    });
    expect(rows.map((r) => (r.peak ?? r.offpeak).terminus_crs)).toEqual(["VIC", "LBG", "BFR"]);
    expect(rows[0].offpeak.terminus_crs).toBe("VIC");
    expect(rows[2].peak).toBeNull();
  });

  it("marks a peak-only terminus (and a station with no off-peak list at all)", () => {
    const rows = mergeTermini({ peak: { termini: [T("LBG", "London Bridge")] }, offpeak: { termini: [] } });
    expect(rows).toHaveLength(1);
    expect(rows[0].offpeak).toBeNull();
    expect(mergeTermini({ peak: { termini: [T("LBG", "x")] } })[0].offpeak).toBeNull();
    expect(mergeTermini(undefined)).toEqual([]);
  });
});

describe("Commute merged rows", () => {
  function station(termini) {
    return { stations: [{ name: "Crystal Palace", crs: "CYP", distance: 0.3, error: null, termini }] };
  }

  it("shows peak and off-peak figures on one row, in peak order", async () => {
    api.commute.mockResolvedValue(
      station({
        peak: { termini: [T("VIC", "London Victoria", { journey_time_mins: 28 }), T("LBG", "London Bridge")] },
        offpeak: { termini: [T("LBG", "London Bridge"), T("VIC", "London Victoria", { journey_time_mins: 27.5 })] },
      })
    );
    render(<Commute listingId={1} ready={true} />);
    const names = await screen.findAllByText(/^London (Victoria|Bridge)$/);
    expect(names.map((n) => n.textContent)).toEqual(["London Victoria", "London Bridge"]);
    expect(screen.getByText(/^28m/)).toBeInTheDocument();
    expect(screen.getByText(/^27.5m/)).toBeInTheDocument();
    expect(screen.queryByText("No off-peak")).not.toBeInTheDocument();
  });

  it("says 'No off-peak' for a peak-only terminus and 'No peak' for an off-peak-only one", async () => {
    api.commute.mockResolvedValue(
      station({
        peak: { termini: [T("LBG", "London Bridge")] },
        offpeak: { termini: [T("BFR", "London Blackfriars")] },
      })
    );
    render(<Commute listingId={1} ready={true} />);
    expect(await screen.findByText("No off-peak")).toBeInTheDocument();
    expect(screen.getByText("No peak")).toBeInTheDocument();
    expect(screen.getAllByText(/^20m/)).toHaveLength(2); // peak (LBG) + off-peak (BFR)
  });
});

describe("Commute row layout", () => {
  it("lays out name, operators, interchange, peak, also-to CRS codes, off-peak in grid order", async () => {
    api.commute.mockResolvedValue({
      stations: [
        {
          name: "East Croydon", crs: "ECR", distance: 0.4, error: null,
          termini: {
            peak: {
              termini: [
                T("LBG", "London Bridge", {
                  operators_title: "Southern, Thameslink",
                  tube_lines: [{ line: "Northern", color: "#000000" }],
                  also_calls_at: [
                    { terminus_crs: "CST", terminus_name: "London Cannon Street" },
                    { terminus_crs: "CHX", terminus_name: "London Charing Cross" },
                  ],
                }),
              ],
            },
            offpeak: { termini: [T("LBG", "London Bridge", { journey_time_mins: 21 })] },
          },
        },
      ],
    });
    const { container } = render(<Commute listingId={1} ready={true} />);
    const row = await waitFor(() => {
      const r = container.querySelector(".commute-terminus-row");
      expect(r).not.toBeNull();
      return r;
    });
    const cells = Array.from(row.children);
    expect(cells).toHaveLength(6);
    expect(cells[0]).toHaveTextContent("London Bridge");
    expect(cells[1]).toHaveTextContent(/Southern.*Thameslink/);
    expect(cells[2]).toHaveTextContent("Northern");
    expect(cells[3]).toHaveTextContent(/^20m/);
    expect(cells[4]).toHaveTextContent("also to CST, CHX");
    expect(cells[5]).toHaveTextContent(/^21m/);
  });

  it("leaves the also-to cell empty when there is none, keeping the six-cell grid", async () => {
    api.commute.mockResolvedValue({
      stations: [
        { name: "Mitcham Eastfields", crs: "MTC", distance: 0.5, error: null,
          termini: { peak: { termini: [T("LBG", "London Bridge")] }, offpeak: { termini: [] } } },
      ],
    });
    const { container } = render(<Commute listingId={1} ready={true} />);
    const row = await waitFor(() => {
      const r = container.querySelector(".commute-terminus-row");
      expect(r).not.toBeNull();
      return r;
    });
    expect(row.children).toHaveLength(6);
    expect(row.children[4]).toBeEmptyDOMElement();
    expect(row.children[5]).toHaveTextContent("No off-peak");
  });

  it("takes identity from the off-peak side when only it exists, and puts 'No peak' in the peak cell", async () => {
    api.commute.mockResolvedValue({
      stations: [
        { name: "Woking", crs: "WOK", distance: 0.3, error: null,
          termini: {
            peak: { termini: [] },
            offpeak: { termini: [T("BFR", "London Blackfriars", {
              operators_title: "Thameslink",
              also_calls_at: [{ terminus_crs: "STP", terminus_name: "London St Pancras International" }],
            })] },
          } },
      ],
    });
    const { container } = render(<Commute listingId={1} ready={true} />);
    const row = await waitFor(() => {
      const r = container.querySelector(".commute-terminus-row");
      expect(r).not.toBeNull();
      return r;
    });
    const cells = Array.from(row.children);
    expect(cells[0]).toHaveTextContent("London Blackfriars");
    expect(cells[1]).toHaveTextContent(/Thameslink/);
    expect(cells[2]).toBeEmptyDOMElement(); // no tube lines
    expect(cells[3]).toHaveTextContent("No peak");
    expect(cells[4]).toHaveTextContent("also to STP");
    expect(cells[5]).toHaveTextContent(/^20m/);
  });

  it("skips also_calls_at entries that lack a CRS code", async () => {
    api.commute.mockResolvedValue({
      stations: [
        { name: "Woking", crs: "WOK", distance: 0.3, error: null,
          termini: {
            peak: { termini: [T("LBG", "London Bridge", { also_calls_at: [{ terminus_name: "x" }, { terminus_crs: "CHX", terminus_name: "y" }] })] },
            offpeak: { termini: [] },
          } },
      ],
    });
    render(<Commute listingId={1} ready={true} />);
    expect(await screen.findByText("also to CHX")).toBeInTheDocument();
  });
});
