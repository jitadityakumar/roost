import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FloorplanTracer from "../components/FloorplanTracer.jsx";

// Canvas pointer interaction isn't meaningfully testable in jsdom (no real
// rendering/hit-testing) -- this just confirms the component mounts, wires
// up the toolbar, and the room-type buttons add rooms to the sidebar
// (state changes outside the canvas itself, which jsdom does exercise).
describe("FloorplanTracer", () => {
  it("renders the toolbar and an empty room list", () => {
    render(
      <FloorplanTracer
        imageSrc={null}
        initialRooms={[]}
        initialShapes={[]}
        initialScale={null}
        onSave={vi.fn()}
        saving={false}
      />
    );
    expect(screen.getByText("Select")).toBeInTheDocument();
    expect(screen.getByText("Rect")).toBeInTheDocument();
    expect(screen.getByText("Polygon")).toBeInTheDocument();
    expect(screen.getByText("Calibrate")).toBeInTheDocument();
    expect(screen.getByText("scale not set")).toBeInTheDocument();
  });

  it("adding a room type creates a numbered room in the sidebar", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <FloorplanTracer
        imageSrc={null}
        initialRooms={[]}
        initialShapes={[]}
        initialScale={null}
        onSave={vi.fn()}
        saving={false}
      />
    );
    await user.click(screen.getByText("+ Bedroom"));
    expect(screen.getByDisplayValue("Bedroom 1")).toBeInTheDocument();
    await user.click(screen.getByText("+ Bedroom"));
    expect(screen.getByDisplayValue("Bedroom 2")).toBeInTheDocument();
  });

  it("calls onSave with the current rooms/shapes/scale", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <FloorplanTracer
        imageSrc={null}
        initialRooms={[{ id: "r1", name: "Bedroom 1", color: "#2e7d6b", type: "bedroom" }]}
        initialShapes={[]}
        initialScale={12.5}
        onSave={onSave}
        saving={false}
      />
    );
    await user.click(screen.getByText("Save"));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        rooms: [{ id: "r1", name: "Bedroom 1", color: "#2e7d6b", type: "bedroom" }],
        shapes: [],
        activeScale: 12.5,
      })
    );
  });

  it("'Clear all shapes & rooms' removes rooms too, so re-adding a type doesn't create duplicates", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <FloorplanTracer
        imageSrc={null}
        initialRooms={[{ id: "r1", name: "Bedroom 1", color: "#2e7d6b", type: "bedroom" }]}
        initialShapes={[]}
        initialScale={12.5}
        onSave={vi.fn()}
        saving={false}
      />
    );
    expect(screen.getByDisplayValue("Bedroom 1")).toBeInTheDocument();
    await user.click(screen.getByText("Clear all shapes & rooms"));
    expect(screen.queryByDisplayValue("Bedroom 1")).not.toBeInTheDocument();
    await user.click(screen.getByText("+ Bedroom"));
    expect(screen.getByDisplayValue("Bedroom 1")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Bedroom 2")).not.toBeInTheDocument();
  });
});
