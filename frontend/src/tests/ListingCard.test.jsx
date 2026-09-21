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

describe("ListingCard fact tags", () => {
  it("shows floor area, EPC, chain free and lease years with threshold colours", () => {
    renderCard(
      makeListing({
        floor_area_sqft: 1180,
        epc_current: "C (71)",
        chain_free: true,
        lease_years_remaining: 96,
        field_colors: { floor_area_sqft: "green", epc_current: "amber", lease_years_remaining: "red" },
      })
    );
    expect(screen.getByText("1,180 sq ft")).toHaveClass("tc-green");
    expect(screen.getByText("C (71)")).toHaveClass("tc-amber");
    expect(screen.getByText("Chain free")).toHaveClass("tc-green");
    expect(screen.getByText("96 years")).toHaveClass("tc-red");
  });

  it("omits tags for unknown values and for chain free unless Yes", () => {
    renderCard(makeListing({ chain_free: false, floor_area_sqft: null, epc_current: null, lease_years_remaining: null }));
    expect(screen.queryByText("Chain free")).not.toBeInTheDocument();
    expect(screen.queryByText(/sq ft/)).not.toBeInTheDocument();
    expect(screen.queryByText(/years/)).not.toBeInTheDocument();
  });

  it("renders a tag without colour when no threshold rule applies", () => {
    renderCard(makeListing({ floor_area_sqft: 700, field_colors: {} }));
    expect(screen.getByText("700 sq ft")).not.toHaveClass("tc-green");
  });
});

describe("ListingCard fact tag edge cases", () => {
  it("still renders zero-valued floor area and lease years", () => {
    renderCard(makeListing({ floor_area_sqft: 0, lease_years_remaining: 0 }));
    expect(screen.getByText("0 sq ft")).toBeInTheDocument();
    expect(screen.getByText("0 years")).toBeInTheDocument();
  });

  it("uses singular 'year' for a lease of 1", () => {
    renderCard(makeListing({ lease_years_remaining: 1 }));
    expect(screen.getByText("1 year")).toBeInTheDocument();
  });

  it("renders chain free green even when field_colors is absent", () => {
    renderCard(makeListing({ chain_free: true, field_colors: undefined }));
    expect(screen.getByText("Chain free")).toHaveClass("tc-green");
  });
});
