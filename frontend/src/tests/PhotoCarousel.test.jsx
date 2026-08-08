import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PhotoCarousel from "../components/PhotoCarousel.jsx";

const IMAGES = ["/a.jpg", "/b.jpg", "/c.jpg"];

describe("PhotoCarousel", () => {
  it("renders nothing when there are no images", () => {
    const { container } = render(<PhotoCarousel images={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not show nav controls for a single image", () => {
    render(<PhotoCarousel images={["/a.jpg"]} />);
    expect(screen.queryByLabelText("Next photo")).not.toBeInTheDocument();
  });

  it("advances forward and wraps around at the end", () => {
    render(<PhotoCarousel images={IMAGES} />);
    const next = screen.getByLabelText("Next photo");

    fireEvent.click(next);
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    fireEvent.click(next);
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    fireEvent.click(next);
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("goes back and wraps around at the start", () => {
    render(<PhotoCarousel images={IMAGES} />);
    fireEvent.click(screen.getByLabelText("Previous photo"));
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
  });

  it("navigates with arrow keys", () => {
    render(<PhotoCarousel images={IMAGES} />);
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("ignores arrow keys typed into a form field", () => {
    render(
      <div>
        <input data-testid="some-input" />
        <PhotoCarousel images={IMAGES} />
      </div>
    );
    fireEvent.keyDown(screen.getByTestId("some-input"), { key: "ArrowRight" });
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("advances on a leftward swipe past the threshold", () => {
    render(<PhotoCarousel images={IMAGES} />);
    const main = document.querySelector(".photo-carousel-main");

    fireEvent.touchStart(main, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(main, { changedTouches: [{ clientX: 150 }] }); // delta -50, past -40

    expect(screen.getByText("2 / 3")).toBeInTheDocument();
  });

  it("does not change the photo for a swipe under the threshold", () => {
    render(<PhotoCarousel images={IMAGES} />);
    const main = document.querySelector(".photo-carousel-main");

    fireEvent.touchStart(main, { touches: [{ clientX: 200 }] });
    fireEvent.touchEnd(main, { changedTouches: [{ clientX: 190 }] }); // delta -10

    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("resets to the first image when the images prop changes", () => {
    const { rerender } = render(<PhotoCarousel images={IMAGES} />);
    fireEvent.click(screen.getByLabelText("Next photo"));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();

    rerender(<PhotoCarousel images={["/x.jpg", "/y.jpg"]} />);
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });
});
