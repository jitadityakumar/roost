import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import Comments from "../components/Comments.jsx";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
  api: {
    comments: {
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    },
  },
}));

function listingWith(comments) {
  return { id: 1, comments };
}

beforeEach(() => {
  vi.clearAllMocks();
  document.cookie.split(";").forEach((c) => {
    const name = c.split("=")[0].trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/`;
  });
});

describe("Comments", () => {
  it("shows an empty state when there are no comments", () => {
    render(<Comments listing={listingWith([])} onUpdate={() => {}} />);
    expect(screen.getByText("No comments yet.")).toBeInTheDocument();
  });

  it("renders comments most-recent-first as already ordered by the API", () => {
    render(
      <Comments
        listing={listingWith([
          { id: 2, comment_type: "general", text: "Second", initials: "AB", created_at: "2026-01-02T00:00:00Z" },
          { id: 1, comment_type: "rejection", text: "First", initials: "JK", created_at: "2026-01-01T00:00:00Z" },
        ])}
        onUpdate={() => {}}
      />
    );
    const rows = screen.getAllByText(/Second|First/);
    expect(rows[0]).toHaveTextContent("Second");
    expect(rows[1]).toHaveTextContent("First");
  });

  it("renders a dash for null created_at and null initials", () => {
    render(
      <Comments
        listing={listingWith([{ id: 1, comment_type: "general", text: "Backfilled", initials: null, created_at: null }])}
        onUpdate={() => {}}
      />
    );
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(1);
  });

  it("adds a comment, prefilling initials from a saved cookie on the next open", async () => {
    const user = userEvent.setup();
    const updated = listingWith([{ id: 1, comment_type: "general", text: "Nice garden", initials: "JK", created_at: "2026-01-01T00:00:00Z" }]);
    api.comments.create.mockResolvedValue(updated);

    const { rerender } = render(<Comments listing={listingWith([])} onUpdate={() => {}} />);
    await user.click(screen.getByText("+ Add comment"));
    await user.type(screen.getByLabelText("Initials"), "JK");
    await user.type(screen.getByLabelText("Comment"), "Nice garden");
    await user.click(screen.getByText("Save"));

    await waitFor(() => expect(api.comments.create).toHaveBeenCalledWith(1, { text: "Nice garden", initials: "JK" }));

    rerender(<Comments listing={listingWith([])} onUpdate={() => {}} />);
    await user.click(screen.getByText("+ Add comment"));
    expect(screen.getByLabelText("Initials")).toHaveValue("JK");
  });

  it("shows a validation error on blank initials without calling the API", async () => {
    const user = userEvent.setup();
    render(<Comments listing={listingWith([])} onUpdate={() => {}} />);
    await user.click(screen.getByText("+ Add comment"));
    await user.type(screen.getByLabelText("Comment"), "Nice garden");
    await user.click(screen.getByText("Save"));

    expect(await screen.findByText(/required/)).toBeInTheDocument();
    expect(api.comments.create).not.toHaveBeenCalled();
  });

  it("edits an existing comment", async () => {
    const user = userEvent.setup();
    const original = { id: 1, comment_type: "general", text: "Original", initials: "JK", created_at: "2026-01-01T00:00:00Z" };
    const updated = listingWith([{ ...original, text: "Edited" }]);
    api.comments.update.mockResolvedValue(updated);

    render(<Comments listing={listingWith([original])} onUpdate={() => {}} />);
    await user.click(screen.getByLabelText("Edit comment"));
    const textField = screen.getByLabelText("Comment");
    await user.clear(textField);
    await user.type(textField, "Edited");
    await user.click(screen.getByText("Save"));

    await waitFor(() =>
      expect(api.comments.update).toHaveBeenCalledWith(1, 1, { text: "Edited", initials: "JK" })
    );
  });

  it("deletes a comment after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const comment = { id: 1, comment_type: "general", text: "Bye", initials: "JK", created_at: "2026-01-01T00:00:00Z" };
    api.comments.remove.mockResolvedValue(listingWith([]));

    render(<Comments listing={listingWith([comment])} onUpdate={() => {}} />);
    await user.click(screen.getByLabelText("Delete comment"));

    await waitFor(() => expect(api.comments.remove).toHaveBeenCalledWith(1, 1));
  });
});
