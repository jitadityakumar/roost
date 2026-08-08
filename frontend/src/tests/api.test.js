import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api.js";

function mockFetch({ ok, status = 200, json, jsonThrows = false }) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "Error",
    json: jsonThrows ? async () => { throw new Error("bad json"); } : async () => json,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api request()", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch({ ok: true, json: { id: 1, address: "1 Test St" } });

    const result = await api.get(1);

    expect(result).toEqual({ id: 1, address: "1 Test St" });
    expect(global.fetch).toHaveBeenCalledWith("/api/listings/1", expect.any(Object));
  });

  it("returns null for a 204 response", async () => {
    mockFetch({ ok: true, status: 204, json: null });

    const result = await api.remove(1);

    expect(result).toBeNull();
  });

  it("throws the server-provided detail message on a non-ok response", async () => {
    mockFetch({ ok: false, status: 422, json: { detail: "invalid url" } });

    await expect(api.create("bad-url")).rejects.toThrow("invalid url");
  });

  it("falls back to a generic message when the error body isn't JSON", async () => {
    mockFetch({ ok: false, status: 500, jsonThrows: true });

    await expect(api.get(1)).rejects.toThrow("500 Error");
  });
});

describe("api.list", () => {
  it("omits the query string when no status is given", async () => {
    mockFetch({ ok: true, json: [] });
    await api.list();
    expect(global.fetch).toHaveBeenCalledWith("/api/listings", expect.any(Object));
  });

  it("includes user_status when given", async () => {
    mockFetch({ ok: true, json: [] });
    await api.list("active");
    expect(global.fetch).toHaveBeenCalledWith("/api/listings?user_status=active", expect.any(Object));
  });
});

describe("api.mediaUrl", () => {
  it("builds the expected media URL", () => {
    expect(api.mediaUrl(1, "photos", "01.jpeg")).toBe("/api/listings/1/media/photos/01.jpeg");
  });
});
