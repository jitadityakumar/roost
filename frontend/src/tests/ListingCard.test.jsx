import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ListingCard from "../components/ListingCard.jsx";

vi.mock("../api.js", () => ({
  api: {
    mediaList: vi.fn().mockResolvedValue({ photos: [] }),
    mediaUrl: (id, category, filename) => `/media/${id}/${category}/${filename}`,
  },
}));

function makeListing(overrides = {}) {
  return {
    id: 1,
    url: "https://www.rightmove.co.uk/properties/1",
    extraction_status: "done",
    pipeline_status: null,
    user_status: "triage",
    price_gbp: 500000,
    address: "1 Test Street",
    bedrooms: 2,
    bathrooms: 1,
    property_type: "Flat",
    ...overrides,
  };
}

function renderCard(listing) {
  return render(
    <MemoryRouter>
      <ListingCard listing={listing} />
    </MemoryRouter>
  );
}

describe("ListingCard pipeline status", () => {
  it("shows a stub card with 'Queued' before extraction fields exist", () => {
    renderCard(makeListing({ extraction_status: "queued", pipeline_status: "queued" }));
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("shows the Rightmove URL and a 'Fetching details…' message while still fetching", () => {
    renderCard(makeListing({ extraction_status: "running", pipeline_status: "fetching" }));
    expect(screen.getByText("Fetching details…")).toBeInTheDocument();
  });

  it("shows the extraction error on a permanently failed stub", () => {
    renderCard(
      makeListing({
        extraction_status: "failed",
        pipeline_status: "failed",
        extraction_error: "Rightmove returned 403",
      })
    );
    expect(screen.getByText("Rightmove returned 403")).toBeInTheDocument();
  });

  it("renders the real card with no pipeline badge once everything is done", () => {
    renderCard(makeListing({ pipeline_status: null }));
    expect(screen.getByText("1 Test Street")).toBeInTheDocument();
    expect(screen.queryByText("Processing…")).not.toBeInTheDocument();
    expect(screen.queryByText("Fetching details…")).not.toBeInTheDocument();
  });

  it("shows a 'Processing…' badge on the real card while llm-lane jobs run", () => {
    renderCard(makeListing({ pipeline_status: "processing" }));
    expect(screen.getByText("1 Test Street")).toBeInTheDocument();
    expect(screen.getByText("Processing…")).toBeInTheDocument();
  });
});

describe("ListingCard warning indicator", () => {
  it("shows a warning dot once processing is done and the listing has a standards violation", () => {
    renderCard(makeListing({ pipeline_status: null, has_warning: true }));
    expect(document.querySelector(".warning-dot")).toBeInTheDocument();
  });

  it("shows no warning dot when the listing has no violation", () => {
    renderCard(makeListing({ pipeline_status: null, has_warning: false }));
    expect(document.querySelector(".warning-dot")).not.toBeInTheDocument();
  });

  it("hides the warning dot while still processing, even if has_warning is true", () => {
    renderCard(makeListing({ pipeline_status: "processing", has_warning: true }));
    expect(document.querySelector(".warning-dot")).not.toBeInTheDocument();
  });
});
