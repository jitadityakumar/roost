const BASE = "/api/listings";
const STANDARDS_BASE = "/api/standards/rules";

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
  mediaList: (id) => request(`/${id}/media`),
  mediaUrl: (id, category, filename) => `${BASE}/${id}/media/${category}/${filename}`,

  standards: {
    list: () => requestFrom(STANDARDS_BASE, ""),
    create: (body) => requestFrom(STANDARDS_BASE, "", { method: "POST", body: JSON.stringify(body) }),
    patch: (id, body) => requestFrom(STANDARDS_BASE, `/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    remove: (id) => requestFrom(STANDARDS_BASE, `/${id}`, { method: "DELETE" }),
  },
};
