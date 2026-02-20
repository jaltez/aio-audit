const API_ROOT = import.meta.env.VITE_API_ROOT ?? "";
const FALLBACK_API_ROOT = "http://127.0.0.1:8000";

async function request(path) {
  const primaryUrl = `${API_ROOT}${path}`;
  try {
    const res = await fetch(primaryUrl);
    if (!res.ok) {
      throw new Error(`API request failed (${res.status}) for ${primaryUrl}`);
    }
    return res.json();
  } catch (err) {
    const shouldTryFallback = !API_ROOT;
    if (!shouldTryFallback) {
      throw err;
    }

    const fallbackUrl = `${FALLBACK_API_ROOT}${path}`;
    const fallbackRes = await fetch(fallbackUrl);
    if (!fallbackRes.ok) {
      throw new Error(`API request failed (${fallbackRes.status}) for ${fallbackUrl}`);
    }
    return fallbackRes.json();
  }
}

export function getSessions() {
  return request("/api/sessions");
}

export function getSummary(sessionId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/summary`);
}

export function getPages(sessionId, params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((v) => q.append(key, String(v)));
    } else {
      q.set(key, String(value));
    }
  });
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/pages?${q.toString()}`);
}

export function getPageDetail(sessionId, pageId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}`);
}

export function csvExportUrl(sessionId, params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((v) => q.append(key, String(v)));
    } else {
      q.set(key, String(value));
    }
  });
  return `${API_ROOT}/api/sessions/${encodeURIComponent(sessionId)}/exports.csv?${q.toString()}`;
}

export function jsonExportUrl(sessionId, params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((v) => q.append(key, String(v)));
    } else {
      q.set(key, String(value));
    }
  });
  return `${API_ROOT}/api/sessions/${encodeURIComponent(sessionId)}/exports.json?${q.toString()}`;
}
