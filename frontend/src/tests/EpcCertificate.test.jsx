import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import EpcCertificate from "../components/EpcCertificate.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: { setEpcCertificate: vi.fn(), removeEpcCertificate: vi.fn() },
}));

const URL = "https://find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000";

const CERT = {
  address: "Flat 1, 1, Example Road, TOWNSVILLE, AB1 2CD",
  postcode: "AB1 2CD",
  postcode_mismatch: false,
  current_rating: "D",
  current_score: 62,
  potential_rating: "B",
  potential_score: 84,
  certificate_date: "2021-03-06",
  valid_until: "2031-03-05",
  features: [
    { feature: "Wall", description: "Solid brick", rating: "Poor" },
    { feature: "Roof", description: "(another dwelling above)", rating: "N/A" },
  ],
  steps: [
    { step: 1, title: "Wall insulation", installation_cost: "£7,500 - £11,000", yearly_saving_gbp: 1240, potential_rating: "78 C" },
    { step: 2, title: "Low energy lighting", installation_cost: null, yearly_saving_gbp: null, potential_rating: null },
  ],
};

const base = { id: 1, postcode: "AB1 2CD", epc_certificate_url: null, epc_certificate: null };

function renderIt(listing, extra = {}) {
  const props = { job: undefined, onUpdate: vi.fn(), onReload: vi.fn(), ...extra };
  render(<EpcCertificate listing={{ ...base, ...listing }} {...props} />);
  return props;
}

beforeEach(() => vi.clearAllMocks());

describe("EpcCertificate", () => {
  it("offers an attach form when no certificate is attached", async () => {
    api.setEpcCertificate.mockResolvedValue({ ...base, epc_certificate_url: URL });
    const { onUpdate } = renderIt({});
    fireEvent.change(screen.getByLabelText("EPC certificate URL"), { target: { value: `  ${URL} ` } });
    fireEvent.click(screen.getByRole("button", { name: "Attach certificate" }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalled());
    expect(api.setEpcCertificate).toHaveBeenCalledWith(1, URL);
  });

  it("shows the server's validation error", async () => {
    api.setEpcCertificate.mockRejectedValue(new Error("not a certificate URL"));
    renderIt({});
    fireEvent.change(screen.getByLabelText("EPC certificate URL"), { target: { value: "https://x.test/a" } });
    fireEvent.click(screen.getByRole("button", { name: "Attach certificate" }));
    expect(await screen.findByText("not a certificate URL")).toBeInTheDocument();
  });

  it("polls while the fetch job is in flight", () => {
    vi.useFakeTimers();
    const { onReload } = renderIt(
      { epc_certificate_url: URL },
      { job: { job_type: "epc_certificate_fetch", status: "running" } },
    );
    expect(screen.getByText("Fetching certificate…")).toBeInTheDocument();
    vi.advanceTimersByTime(2100);
    expect(onReload).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("shows the job error and retry hint when the fetch failed, without polling", () => {
    vi.useFakeTimers();
    const { onReload } = renderIt(
      { epc_certificate_url: URL },
      { job: { status: "failed", last_error: "certificate not found (404)" } },
    );
    expect(screen.getByText(/certificate not found \(404\)/)).toBeInTheDocument();
    vi.advanceTimersByTime(5000);
    expect(onReload).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("renders address, ratings, validity, features and steps", () => {
    renderIt({ epc_certificate_url: URL, epc_certificate: CERT }, { job: { status: "done" } });
    expect(screen.getByText(CERT.address)).toBeInTheDocument();
    expect(screen.getByText("D (62)")).toBeInTheDocument();
    expect(screen.getByText("B (84)")).toBeInTheDocument();
    expect(screen.getByText(/Certificate dated 6 March 2021/)).toBeInTheDocument();
    expect(screen.getByText(/Valid until 5 March 2031/)).toBeInTheDocument();
    expect(screen.getByText("Breakdown of property’s energy performance")).toBeInTheDocument();
    expect(screen.getByText("Solid brick")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.getByText("Steps you could take to save energy")).toBeInTheDocument();
    expect(screen.getByText("£7,500 - £11,000")).toBeInTheDocument();
    expect(screen.getByText("£1,240")).toBeInTheDocument();
    expect(screen.getByText("78 C")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("flags an expired certificate", () => {
    renderIt({ epc_certificate_url: URL, epc_certificate: { ...CERT, valid_until: "2020-01-01" } });
    expect(screen.getByText(/Expired 1 January 2020/)).toBeInTheDocument();
  });

  it("warns on a postcode mismatch", () => {
    renderIt({
      postcode: "ZZ9 9ZZ",
      epc_certificate_url: URL,
      epc_certificate: { ...CERT, postcode_mismatch: true },
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/AB1 2CD.*ZZ9 9ZZ/);
  });

  it("removes the certificate after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    api.removeEpcCertificate.mockResolvedValue({ ...base });
    const { onUpdate } = renderIt({ epc_certificate_url: URL, epc_certificate: CERT });
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(onUpdate).toHaveBeenCalled());
    expect(api.removeEpcCertificate).toHaveBeenCalledWith(1);
  });

  it("does not remove when the confirm is declined", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIt({ epc_certificate_url: URL, epc_certificate: CERT });
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(api.removeEpcCertificate).not.toHaveBeenCalled();
  });
});
