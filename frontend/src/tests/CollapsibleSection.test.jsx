import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import CollapsibleSection from "../components/CollapsibleSection.jsx";

describe("CollapsibleSection", () => {
  it("renders expanded when defaultExpanded is true", () => {
    render(
      <CollapsibleSection title="Commute" defaultExpanded={true}>
        <p>Commute body</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("Commute body")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Commute/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("renders collapsed when defaultExpanded is false", () => {
    render(
      <CollapsibleSection title="Commute" defaultExpanded={false}>
        <p>Commute body</p>
      </CollapsibleSection>
    );
    expect(screen.queryByText("Commute body")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Commute/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("clicking the header toggle flips expanded state", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection title="Commute" defaultExpanded={false}>
        <p>Commute body</p>
      </CollapsibleSection>
    );
    const toggle = screen.getByRole("button", { name: /Commute/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Commute body")).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Commute body")).not.toBeInTheDocument();
  });

  it("shows emptyMessage when hasData is false and expanded", () => {
    render(
      <CollapsibleSection title="Nearest stations" defaultExpanded={true} hasData={false} emptyMessage="No nearby stations found.">
        <p>Real content</p>
      </CollapsibleSection>
    );
    expect(screen.getByText("No nearby stations found.")).toBeInTheDocument();
    expect(screen.queryByText("Real content")).not.toBeInTheDocument();
  });

  it("hides the body when collapsed regardless of hasData", () => {
    render(
      <CollapsibleSection title="Nearest stations" defaultExpanded={false} hasData={false} emptyMessage="No nearby stations found.">
        <p>Real content</p>
      </CollapsibleSection>
    );
    expect(screen.queryByText("No nearby stations found.")).not.toBeInTheDocument();
    expect(screen.queryByText("Real content")).not.toBeInTheDocument();
  });

  it("renders actions regardless of expanded state", () => {
    const { rerender } = render(
      <CollapsibleSection title="Frequent destinations" defaultExpanded={false} actions={<button>Refresh</button>}>
        <p>body</p>
      </CollapsibleSection>
    );
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();

    rerender(
      <CollapsibleSection title="Frequent destinations" defaultExpanded={true} actions={<button>Refresh</button>}>
        <p>body</p>
      </CollapsibleSection>
    );
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });
});
