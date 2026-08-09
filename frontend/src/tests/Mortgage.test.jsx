import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Mortgage from "../components/Mortgage.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { mortgage: vi.fn() },
}));

describe("Mortgage", () => {
  it("shows a waiting message when the listing isn't ready yet", () => {
    render(<Mortgage listingId={1} priceGbp={425000} ready={false} />);
    expect(screen.getByText(/Waiting for listing details/)).toBeInTheDocument();
    expect(api.mortgage).not.toHaveBeenCalled();
  });

  it("shows a no-price message without calling the API", () => {
    render(<Mortgage listingId={1} priceGbp={null} ready={true} />);
    expect(screen.getByText(/No price on this listing yet/)).toBeInTheDocument();
    expect(api.mortgage).not.toHaveBeenCalled();
  });

  it("shows a loading state then renders the summary rows on success", async () => {
    api.mortgage.mockResolvedValue({
      result: {
        monthlyPayments: [{ fromMonth: 1, payment: 1832.5, isVariable: false }],
        payoffMonth: 301,
        sdltPaid: 11250,
        totalInterestPaid: 250000,
        totalPaid: 686250,
      },
      error: null,
    });

    render(<Mortgage listingId={1} priceGbp={425000} ready={true} />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("£1,833")).toBeInTheDocument());
    expect(screen.getByText("Initial monthly payment")).toBeInTheDocument();
    expect(screen.getByText("25y")).toBeInTheDocument();
    expect(screen.getByText("£11,250")).toBeInTheDocument();
    expect(screen.getByText("£250,000")).toBeInTheDocument();
    expect(screen.getByText("£686,250")).toBeInTheDocument();
    expect(screen.getByText("£425,000")).toBeInTheDocument();
    expect(screen.queryByText("Monthly payment over time")).not.toBeInTheDocument();
  });

  it("renders the monthly-payments-over-time list only when there's more than one period", async () => {
    api.mortgage.mockResolvedValue({
      result: {
        monthlyPayments: [
          { fromMonth: 1, payment: 1832, isVariable: false },
          { fromMonth: 61, payment: 2100, isVariable: true },
        ],
        payoffMonth: 301,
        sdltPaid: 11250,
        totalInterestPaid: 250000,
        totalPaid: 686250,
      },
      error: null,
    });

    render(<Mortgage listingId={1} priceGbp={425000} ready={true} />);

    await waitFor(() => expect(screen.getByText("Monthly payment over time")).toBeInTheDocument());
    expect(screen.getByText("From the start (fixed)")).toBeInTheDocument();
    expect(screen.getByText("5y (variable)")).toBeInTheDocument();
    expect(screen.getByText("£2,100/mo")).toBeInTheDocument();
  });

  it("shows an error instead of NaN when the API returns no payment periods", async () => {
    api.mortgage.mockResolvedValue({
      result: {
        monthlyPayments: [],
        payoffMonth: 301,
        sdltPaid: 11250,
        totalInterestPaid: 250000,
        totalPaid: 686250,
      },
      error: null,
    });
    render(<Mortgage listingId={1} priceGbp={425000} ready={true} />);
    await waitFor(() => expect(screen.getByText(/no payment schedule returned/)).toBeInTheDocument());
  });

  it("shows a section-level error when the backend reports one", async () => {
    api.mortgage.mockResolvedValue({ result: null, error: "mortgage API request failed: boom" });
    render(<Mortgage listingId={1} priceGbp={425000} ready={true} />);
    await waitFor(() => expect(screen.getByText(/boom/)).toBeInTheDocument());
  });

  it("shows an error when the request itself fails", async () => {
    api.mortgage.mockRejectedValue(new Error("network down"));
    render(<Mortgage listingId={1} priceGbp={425000} ready={true} />);
    await waitFor(() => expect(screen.getByText(/network down/)).toBeInTheDocument());
  });
});
