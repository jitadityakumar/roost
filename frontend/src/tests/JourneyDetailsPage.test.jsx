import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import JourneyDetailsPage from "../components/JourneyDetailsPage.jsx";
import { api } from "../api.js";
import { logoUrlForType } from "../components/networkLogos.js";

vi.mock("../api.js", () => ({
  api: { journeyScanPool: vi.fn() },
}));

// Deterministic: exercise the letter-badge fallback regardless of whether
// the gitignored real logo files happen to be present on the machine
// running the tests, same precedent as NearestStations.test.jsx.
vi.mock("../components/networkLogos.js", () => ({
  logoUrlForType: vi.fn(() => undefined),
}));

function renderPage(poolId = "42") {
  return render(
    <MemoryRouter initialEntries={[`/journey-details/${poolId}`]}>
      <Routes>
        <Route path="/journey-details/:poolId" element={<JourneyDetailsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function samplePool(overrides = {}) {
  return {
    destination_name: "Office",
    scanned_at: "2026-08-18T14:07:00Z",
    query_params: {
      journeyPreference: "LeastInterchange",
      mode: "national-rail,tube,overground,dlr,tram,elizabeth-line",
      date: "20260825",
      time: "0800",
      to_identifier: "910GPADTON",
    },
    candidates: [
      {
        duration_minutes: 78,
        num_changes: 1,
        kind: "interchange",
        start_time: "2026-08-17T08:04:00",
        arrival_time: "2026-08-17T09:22:00",
        legs: [
          {
            mode: "walking",
            operator: null,
            departure_time: "2026-08-17T08:04:00",
            arrival_time: "2026-08-17T08:25:00",
            duration: 21,
            from: "91 York Road",
            to: "Woking Rail Station",
          },
          {
            mode: "national-rail",
            operator: "South Western Railway",
            departure_time: "2026-08-17T08:25:00",
            arrival_time: "2026-08-17T08:51:00",
            duration: 26,
            from: "Woking Rail Station",
            to: "London Waterloo",
            change_minutes: 8,
          },
          {
            mode: "tube",
            operator: "Northern line",
            departure_time: "2026-08-17T08:59:00",
            arrival_time: "2026-08-17T09:11:00",
            duration: 12,
            from: "London Waterloo",
            to: "Mornington Crescent",
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe("JourneyDetailsPage", () => {
  it("shows a loading state before the fetch resolves", () => {
    api.journeyScanPool.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders header, footer, and a candidate summary row", async () => {
    api.journeyScanPool.mockResolvedValue(samplePool());
    renderPage();

    await waitFor(() => expect(screen.getByText("Office")).toBeInTheDocument());
    expect(screen.getByText("LeastInterchange")).toBeInTheDocument();
    expect(screen.getByText("national-rail,tube,overground,dlr,tram,elizabeth-line")).toBeInTheDocument();
    expect(screen.getByText(/1 change/)).toBeInTheDocument();
  });

  it("expands a candidate to show its legs, including a change-time row only where the gap is non-zero", async () => {
    api.journeyScanPool.mockResolvedValue(samplePool());
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByText(/1 change/)).toBeInTheDocument());
    await user.click(screen.getByText(/1 change/));

    expect(screen.getByText("South Western Railway")).toBeInTheDocument();
    expect(screen.getByText("Northern line")).toBeInTheDocument();
    expect(screen.getAllByText("Walk").length).toBeGreaterThan(0);
    expect(screen.getByText("8m change")).toBeInTheDocument();
  });

  it("renders a real logo image instead of the letter badge when one is available for a leg's mode", async () => {
    vi.mocked(logoUrlForType).mockImplementation((type) =>
      type === "NATIONAL_TRAIN" ? "/fake/national-rail.svg" : undefined
    );
    api.journeyScanPool.mockResolvedValue(samplePool());
    const user = userEvent.setup();
    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText(/1 change/)).toBeInTheDocument());
    await user.click(screen.getByText(/1 change/));

    expect(logoUrlForType).toHaveBeenCalledWith("NATIONAL_TRAIN");
    const logo = container.querySelector("img.jd-leg-badge-logo");
    expect(logo).toHaveAttribute("src", "/fake/national-rail.svg");
    // The tube leg still falls back to the letter badge since only
    // NATIONAL_TRAIN was mocked to have a logo.
    expect(screen.getByText("U")).toBeInTheDocument();
  });

  it("shows an empty state when the pool has no candidates", async () => {
    api.journeyScanPool.mockResolvedValue(samplePool({ candidates: [] }));
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/No candidate journeys stored/)).toBeInTheDocument()
    );
  });

  it("shows an error message when the fetch fails", async () => {
    api.journeyScanPool.mockRejectedValue(new Error("journey scan pool not found"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Couldn't load journey details/)).toBeInTheDocument()
    );
  });
});
