import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import LocalPolitics, {
  formatChange,
  headlineSeats,
  headlineText,
  initials,
} from "../components/LocalPolitics.jsx";
import { readableTextColor } from "../partyColors.js";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { localPolitics: vi.fn(), refreshLocalPolitics: vi.fn() },
}));

const FULL = {
  has_data: true,
  mp: {
    name: "Dame Siobhain McDonagh MP",
    member_id: 1,
    constituency: "Mitcham and Morden",
    party_name: "Labour",
    party_colour: "#d50000",
    result: "Lab hold",
    majority: 18761,
    turnout: 30000,
    electorate: 70000,
    turnout_pct: 42.9,
    thumbnail_url: "https://example.test/1/Thumbnail",
  },
  council: { name: "Merton", county: null, ward: "Colliers Wood", parish: "Merton, unparished area" },
  control: {
    year: 2026,
    previous_year: 2025,
    total: 57,
    majority_threshold: 29,
    headline: { status: "majority", party: "Labour", seats: 32, total: 57 },
    parties: [
      { key: "lab", name: "Labour", seats: 32, share: 56, previous_seats: 30, change: 2 },
      { key: "ld", name: "Liberal Democrats", seats: 19, share: 33, previous_seats: 17, change: 2 },
      { key: "con", name: "Conservative", seats: 4, share: 7, previous_seats: 7, change: -3 },
    ],
  },
};

function renderIt(props = {}) {
  return render(<LocalPolitics listingId={1} ready={true} defaultExpanded={true} {...props} />);
}

describe("LocalPolitics helpers", () => {
  it("initials skips titles", () => {
    expect(initials("Dame Siobhain McDonagh MP")).toBe("SM");
    expect(initials("Mr Paul Kohler MP")).toBe("PK");
    expect(initials("")).toBe("?");
  });

  it("headline wording", () => {
    expect(headlineText({ status: "majority", party: "Labour" })).toBe("Labour majority");
    expect(headlineText({ status: "no_overall_majority", party: "Labour" })).toBe(
      "No overall majority. Labour largest party"
    );
    expect(headlineText({ status: "no_overall_majority", party: null })).toBe("No overall majority");
    expect(headlineSeats({ seats: 32, total: 57 })).toBe("32 of 57 seats");
    expect(headlineSeats({ seats: null, total: 60 })).toBe("60 seats");
  });

  it("formatChange", () => {
    expect(formatChange(null)).toEqual({ text: "—", tone: "muted" });
    expect(formatChange(0)).toEqual({ text: "0", tone: "muted" });
    expect(formatChange(2)).toEqual({ text: "+2", tone: "up" });
    expect(formatChange(-3)).toEqual({ text: "−3", tone: "down" });
  });

  it("readableTextColor picks dark text on light colours", () => {
    expect(readableTextColor("#fff685")).toBe("#1a1a1a");
    expect(readableTextColor("#d50000")).toBe("#fff");
    expect(readableTextColor(null)).toBe("#fff");
  });
});

describe("LocalPolitics", () => {
  it("waits for the listing and makes no call when not ready", () => {
    renderIt({ ready: false });
    expect(screen.getByText(/Waiting for listing details/)).toBeInTheDocument();
    expect(api.localPolitics).not.toHaveBeenCalled();
  });

  it("renders MP, council and council control", async () => {
    api.localPolitics.mockResolvedValue(FULL);
    renderIt();

    expect(await screen.findByText("Dame Siobhain McDonagh MP")).toBeInTheDocument();
    expect(screen.getByText("Labour", { selector: ".lp-pill" })).toBeInTheDocument();
    expect(screen.getByText("18,761")).toBeInTheDocument();
    expect(screen.getByText("42.9%")).toBeInTheDocument();
    expect(screen.getByText("Lab hold")).toBeInTheDocument();
    // council block
    expect(screen.getByText("Merton")).toBeInTheDocument();
    expect(screen.getByText("None (unitary authority)")).toBeInTheDocument();
    expect(screen.getByText("Colliers Wood")).toBeInTheDocument();
    expect(screen.getByText("None (unparished)")).toBeInTheDocument();
    // control
    expect(screen.getByText("Labour majority")).toBeInTheDocument();
    expect(screen.getByText(/32 of 57 seats · as of May 2026/)).toBeInTheDocument();
    expect(screen.getByText("majority: 29")).toBeInTheDocument();
    expect(screen.getByText("vs 2025")).toBeInTheDocument();
    expect(screen.getAllByText("+2", { selector: "td.lp-change-up" })).toHaveLength(2);
    expect(screen.getByText("−3")).toBeInTheDocument();
  });

  it("falls back to an initials circle when the portrait fails to load", async () => {
    api.localPolitics.mockResolvedValue(FULL);
    const { container } = renderIt();
    const img = await waitFor(() => {
      const el = container.querySelector("img.lp-portrait");
      expect(el).not.toBeNull();
      return el;
    });
    expect(img).toHaveAttribute("loading", "lazy");
    img.dispatchEvent(new Event("error"));
    await waitFor(() => expect(container.querySelector(".lp-portrait-fallback")).toHaveTextContent("SM"));
  });

  it("uses neutral grey for a party with no colour", async () => {
    api.localPolitics.mockResolvedValue({
      ...FULL,
      mp: { ...FULL.mp, name: "Sir Speaker MP", party_name: "Speaker", party_colour: null },
    });
    renderIt();
    const pill = await screen.findByText("Speaker");
    expect(pill).toHaveStyle({ background: "#909090" });
  });

  it("shows the seat-data empty state when the council has no composition row", async () => {
    api.localPolitics.mockResolvedValue({ ...FULL, control: null });
    renderIt();
    expect(await screen.findByText(/Council seat data isn't available/)).toBeInTheDocument();
    expect(screen.getByText("Dame Siobhain McDonagh MP")).toBeInTheDocument();
  });

  it("shows the whole-section empty state when nothing resolved", async () => {
    api.localPolitics.mockResolvedValue({ mp: null, council: null, control: null, has_data: false });
    renderIt();
    expect(await screen.findByText(/Nothing could be found for this listing's area yet/)).toBeInTheDocument();
  });

  it("shows a load error", async () => {
    api.localPolitics.mockRejectedValue(new Error("boom"));
    renderIt();
    expect(await screen.findByText(/Couldn't load local politics: boom/)).toBeInTheDocument();
  });

  it("Refresh shows a busy label, then re-renders with the new data", async () => {
    const user = userEvent.setup();
    api.localPolitics.mockResolvedValue({ mp: null, council: null, control: null, has_data: false });
    let resolve;
    api.refreshLocalPolitics.mockReturnValue(new Promise((r) => (resolve = r)));
    renderIt();
    await screen.findByText(/Nothing could be found/);

    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(screen.getByRole("button", { name: "Refreshing…" })).toBeDisabled();

    resolve({ ...FULL, refresh: { ok: true, message: null } });
    expect(await screen.findByText("Dame Siobhain McDonagh MP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
  });

  it("Refresh reporting a partial failure keeps the data and shows the message", async () => {
    const user = userEvent.setup();
    api.localPolitics.mockResolvedValue(FULL);
    api.refreshLocalPolitics.mockResolvedValue({
      ...FULL,
      refresh: { ok: false, message: "the Parliament Members API request failed" },
    });
    renderIt();
    await screen.findByText("Dame Siobhain McDonagh MP");

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Members API request failed");
    expect(screen.getByText("Dame Siobhain McDonagh MP")).toBeInTheDocument();
  });

  it("Refresh request failure keeps the existing data on screen", async () => {
    const user = userEvent.setup();
    api.localPolitics.mockResolvedValue(FULL);
    api.refreshLocalPolitics.mockRejectedValue(new Error("502 Bad Gateway"));
    renderIt();
    await screen.findByText("Dame Siobhain McDonagh MP");

    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh failed: 502 Bad Gateway");
    expect(screen.getByText("Dame Siobhain McDonagh MP")).toBeInTheDocument();
  });
});
