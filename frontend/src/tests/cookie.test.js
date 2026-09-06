import { describe, expect, it, beforeEach } from "vitest";
import { getCookie, setCookie } from "../cookie.js";

describe("cookie helper", () => {
  beforeEach(() => {
    document.cookie.split(";").forEach((c) => {
      const name = c.split("=")[0].trim();
      if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/`;
    });
  });

  it("returns undefined for a missing cookie", () => {
    expect(getCookie("roost_test")).toBeUndefined();
  });

  it("round-trips a set value", () => {
    setCookie("roost_test", "JK", 365);
    expect(getCookie("roost_test")).toBe("JK");
  });

  it("URL-encodes and decodes special characters", () => {
    setCookie("roost_test", "a b;c", 365);
    expect(getCookie("roost_test")).toBe("a b;c");
  });
});
