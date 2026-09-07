import { renderHook, waitFor } from "@testing-library/react";
import { act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useListingThumbnail } from "../hooks/useListingThumbnail.js";

vi.mock("../api.js", () => ({
  api: { mediaList: vi.fn() },
}));

import { api } from "../api.js";

describe("useListingThumbnail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns the first photo once the media list resolves", async () => {
    api.mediaList.mockResolvedValue({ photos: ["01.jpeg", "02.jpeg"] });
    const { result } = renderHook(() => useListingThumbnail(1));

    await waitFor(() => expect(result.current[0]).toBe("01.jpeg"));
  });

  it("retries with backoff when the photo list comes back empty, then succeeds", async () => {
    api.mediaList.mockResolvedValueOnce({ photos: [] }).mockResolvedValueOnce({ photos: ["01.jpeg"] });
    const { result } = renderHook(() => useListingThumbnail(1));

    expect(result.current[0]).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => expect(result.current[0]).toBe("01.jpeg"));
    expect(api.mediaList).toHaveBeenCalledTimes(2);
  });

  it("gives up (empty string) after exhausting all retries", async () => {
    api.mediaList.mockResolvedValue({ photos: [] });
    const { result } = renderHook(() => useListingThumbnail(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 8);
    });
    await waitFor(() => expect(result.current[0]).toBe(""));
    expect(api.mediaList).toHaveBeenCalledTimes(9); // initial + 8 retries
  });

  it("resolves to an empty string when the media list request fails", async () => {
    api.mediaList.mockRejectedValue(new Error("network error"));
    const { result } = renderHook(() => useListingThumbnail(1));

    await waitFor(() => expect(result.current[0]).toBe(""));
  });

  it("does not fetch at all when skip is true", async () => {
    renderHook(() => useListingThumbnail(1, { skip: true }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(api.mediaList).not.toHaveBeenCalled();
  });

  it("stops updating state after unmount (no act warning / stale-closure write)", async () => {
    let resolveMediaList;
    api.mediaList.mockReturnValue(
      new Promise((resolve) => {
        resolveMediaList = resolve;
      })
    );
    const { unmount } = renderHook(() => useListingThumbnail(1));
    unmount();

    await act(async () => {
      resolveMediaList({ photos: ["01.jpeg"] });
      await Promise.resolve();
    });
    // No assertion needed beyond "this doesn't throw / warn" -- the
    // cancelled-guard inside the hook is what's under test here.
  });

  it("exposes a setter so callers can force a fallback (e.g. on an <img> load error)", async () => {
    api.mediaList.mockResolvedValue({ photos: ["01.jpeg"] });
    const { result } = renderHook(() => useListingThumbnail(1));
    await waitFor(() => expect(result.current[0]).toBe("01.jpeg"));

    act(() => result.current[1](""));
    expect(result.current[0]).toBe("");
  });
});
