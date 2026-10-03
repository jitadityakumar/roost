import { describe, expect, it } from "vitest";
import {
  EMPTY_FILTERS,
  activeFilterCount,
  applyFilters,
  deriveOptions,
  epcBand,
  sortListings,
  tenureKey,
  visibleOptions,
} from "../listingFilters.js";

const L = (id, o = {}) => ({ id, created_at: "2026-01-01", ...o });
const ids = (ls) => ls.map((l) => l.id);

describe("helpers", () => {
  it("maps tenure, null and odd values to UNKNOWN", () => {
    expect(tenureKey(L(1, { tenure: "FREEHOLD" }))).toBe("FREEHOLD");
    expect(tenureKey(L(1, { tenure: null }))).toBe("UNKNOWN");
    expect(tenureKey(L(1, { tenure: "weird" }))).toBe("UNKNOWN");
  });
  it("reads the EPC letter from 'C (73)'", () => {
    expect(epcBand(L(1, { epc_current: "C (73)" }))).toBe("C");
    expect(epcBand(L(1, { epc_current: "c" }))).toBe("C");
    expect(epcBand(L(1, { epc_current: null }))).toBeNull();
    expect(epcBand(L(1, { epc_current: "73" }))).toBeNull();
  });
});

describe("applyFilters", () => {
  const data = [
    L(1, { tenure: "FREEHOLD", epc_current: "C (70)", chain_free: true }),
    L(2, { tenure: "LEASEHOLD", epc_current: "D (60)", chain_free: null }),
    L(3, { tenure: "SHARE_OF_FREEHOLD", epc_current: "C (72)", chain_free: false }),
    L(4, { tenure: null, epc_current: null, chain_free: true }),
  ];
  it("returns everything with no filters", () => {
    expect(ids(applyFilters(data, EMPTY_FILTERS))).toEqual([1, 2, 3, 4]);
  });
  it("ORs within a group", () => {
    const f = { ...EMPTY_FILTERS, tenure: ["FREEHOLD", "SHARE_OF_FREEHOLD"] };
    expect(ids(applyFilters(data, f))).toEqual([1, 3]);
  });
  it("matches Unknown tenure", () => {
    expect(ids(applyFilters(data, { ...EMPTY_FILTERS, tenure: ["UNKNOWN"] }))).toEqual([4]);
  });
  it("ANDs between groups", () => {
    const f = { tenure: ["FREEHOLD", "LEASEHOLD"], epc: ["C"], chainFree: true };
    expect(ids(applyFilters(data, f))).toEqual([1]);
  });
  it("chain free keeps only true, off shows null/false too", () => {
    expect(ids(applyFilters(data, { ...EMPTY_FILTERS, chainFree: true }))).toEqual([1, 4]);
  });
  it("counts active filters", () => {
    expect(activeFilterCount({ tenure: ["A", "B"], epc: ["C"], chainFree: true })).toBe(4);
  });
});

describe("options", () => {
  const data = [
    L(1, { tenure: "FREEHOLD", epc_current: "C (70)", chain_free: true }),
    L(2, { tenure: "FREEHOLD", epc_current: "C (71)" }),
    L(3, { tenure: null, epc_current: "E (40)" }),
  ];
  it("derives counts and only offers existing values in fixed order", () => {
    const v = visibleOptions(deriveOptions(data), EMPTY_FILTERS);
    expect(v.tenure.map((o) => [o.value, o.count])).toEqual([["FREEHOLD", 2], ["UNKNOWN", 1]]);
    expect(v.epc.map((o) => [o.value, o.count])).toEqual([["C", 2], ["E", 1]]);
    expect(v.showChainFree).toBe(true);
    expect(v.chainFreeCount).toBe(1);
  });
  it("omits Unknown and chain free when none exist", () => {
    const v = visibleOptions(deriveOptions([L(1, { tenure: "FREEHOLD" })]), EMPTY_FILTERS);
    expect(v.tenure.map((o) => o.value)).toEqual(["FREEHOLD"]);
    expect(v.showChainFree).toBe(false);
  });
  it("keeps a selected value whose last listing vanished, with count 0", () => {
    const filters = { tenure: ["LEASEHOLD"], epc: ["G"], chainFree: true };
    const v = visibleOptions(deriveOptions([L(1, { tenure: "FREEHOLD" })]), filters);
    expect(v.tenure.map((o) => [o.value, o.count])).toEqual([["FREEHOLD", 1], ["LEASEHOLD", 0]]);
    expect(v.epc.map((o) => [o.value, o.count])).toEqual([["G", 0]]);
    expect(v.showChainFree).toBe(true);
    expect(v.chainFreeCount).toBe(0);
  });
});

describe("sortListings", () => {
  const data = [
    L(1, { floor_area_sqft: 800, price_gbp: 500 }),
    L(2, { floor_area_sqft: null, price_gbp: null }),
    L(3, { floor_area_sqft: 600, price_gbp: 700 }),
    L(4, { floor_area_sqft: 1000, price_gbp: 300 }),
  ];
  it("size ascending, missing last", () => {
    expect(ids(sortListings(data, "size_asc"))).toEqual([3, 1, 4, 2]);
  });
  it("size descending, missing last", () => {
    expect(ids(sortListings(data, "size_desc"))).toEqual([4, 1, 3, 2]);
  });
  it("price sorts keep missing last", () => {
    expect(ids(sortListings(data, "price_asc"))).toEqual([4, 1, 3, 2]);
    expect(ids(sortListings(data, "price_desc"))).toEqual([3, 1, 4, 2]);
  });
  it("newest first by default, without mutating input", () => {
    const d = [L(1, { created_at: "2026-01-01" }), L(2, { created_at: "2026-02-01" })];
    expect(ids(sortListings(d, "newest"))).toEqual([2, 1]);
    expect(ids(d)).toEqual([1, 2]);
  });
});
