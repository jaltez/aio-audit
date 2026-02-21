export function scoreColor(score) {
  if (score >= 90) return "#2fb391";
  if (score >= 50) return "#d49b3d";
  return "#cc4f69";
}

export function compactUrl(url, maxLen = 60) {
  if (!url) return "";
  if (url.length <= maxLen) return url;
  if (maxLen <= 3) return ".".repeat(maxLen);
  return `${url.slice(0, maxLen - 3)}...`;
}

export function parseQueryState() {
  const params = new URLSearchParams(window.location.search);
  return {
    session: params.get("session") || "",
    q: params.get("q") || "",
    scoreMin: Number(params.get("scoreMin") || 0),
    scoreMax: Number(params.get("scoreMax") || 100),
    issuesMin: Number(params.get("issuesMin") || 0),
    status: params.getAll("status"),
    pageId: params.get("pageId") || ""
  };
}

export function writeQueryState(state) {
  const params = new URLSearchParams();
  if (state.session) params.set("session", state.session);
  if (state.q) params.set("q", state.q);
  params.set("scoreMin", String(state.scoreMin ?? 0));
  params.set("scoreMax", String(state.scoreMax ?? 100));
  params.set("issuesMin", String(state.issuesMin ?? 0));
  (state.status || []).forEach((s) => params.append("status", s));
  if (state.pageId) params.set("pageId", state.pageId);
  const nextUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState({}, "", nextUrl);
}
