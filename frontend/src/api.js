const BASE = "/api/listings";

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, {
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
  mediaList: (id) => request(`/${id}/media`),
  mediaUrl: (id, category, filename) => `${BASE}/${id}/media/${category}/${filename}`,
};
