const BASE = "/api/listings";
const STANDARDS_BASE = "/api/standards/rules";
const CRIME_BASELINES_BASE = "/api/crime/baselines";
const DESTINATIONS_BASE = "/api/destinations";
const JOURNEY_SCAN_POOLS_BASE = "/api/journey-scan-pools";
const COUNCIL_TAX_BASE = "/api/council-tax";

async function requestFrom(base, path, options) {
  const res = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

const request = (path, options) => requestFrom(BASE, path, options);

export const api = {
  list: (userStatus) =>
    request(userStatus ? `?user_status=${userStatus}` : ""),
  get: (id) => request(`/${id}`),
  create: (url) => request("", { method: "POST", body: JSON.stringify({ url }) }),
  refresh: (id) => request(`/${id}/refresh`, { method: "POST" }),
  patch: (id, body) => request(`/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  remove: (id) => request(`/${id}`, { method: "DELETE" }),
  jobs: (id) => request(`/${id}/jobs`),
  commute: (id) => request(`/${id}/commute`),
  mortgage: (id) => request(`/${id}/mortgage`),
  crime: (id) => request(`/${id}/crime`),
  mediaList: (id) => request(`/${id}/media`),
  mediaUrl: (id, category, filename) => `${BASE}/${id}/media/${category}/${filename}`,

  standards: {
    list: () => requestFrom(STANDARDS_BASE, ""),
    create: (body) => requestFrom(STANDARDS_BASE, "", { method: "POST", body: JSON.stringify(body) }),
    patch: (id, body) => requestFrom(STANDARDS_BASE, `/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    remove: (id) => requestFrom(STANDARDS_BASE, `/${id}`, { method: "DELETE" }),
  },

  crimeBaselines: {
    list: () => requestFrom(CRIME_BASELINES_BASE, ""),
    create: (body) =>
      requestFrom(CRIME_BASELINES_BASE, "", { method: "POST", body: JSON.stringify(body) }),
    remove: (id) => requestFrom(CRIME_BASELINES_BASE, `/${id}`, { method: "DELETE" }),
  },

  destinations: {
    list: () => requestFrom(DESTINATIONS_BASE, ""),
    create: (body) => requestFrom(DESTINATIONS_BASE, "", { method: "POST", body: JSON.stringify(body) }),
    remove: (id) => requestFrom(DESTINATIONS_BASE, `/${id}`, { method: "DELETE" }),
    searchStations: (q) => requestFrom(DESTINATIONS_BASE, `/stations/search?q=${encodeURIComponent(q)}`),
    backfillStatus: (id) => requestFrom(DESTINATIONS_BASE, `/${id}/backfill-status`),
  },

  listingDestinations: (id) => request(`/${id}/destinations`),
  refreshListingDestinations: (id) => request(`/${id}/destinations/refresh`, { method: "POST" }),

  journeyScanPool: (poolId) => requestFrom(JOURNEY_SCAN_POOLS_BASE, `/${poolId}`),

  councilTax: {
    list: () => requestFrom(COUNCIL_TAX_BASE, ""),
    update: (gss, body) => requestFrom(COUNCIL_TAX_BASE, `/${gss}`, { method: "PUT", body: JSON.stringify(body) }),
    remove: (gss) => requestFrom(COUNCIL_TAX_BASE, `/${gss}`, { method: "DELETE" }),
  },
};
