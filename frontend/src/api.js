// Thin client for the FastAPI backend (see backend/app/main.py).
// In dev, Vite proxies /api and /ws to http://localhost:8000 (vite.config.js).
export const API_BASE = "/api";

async function j(resp) {
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export const api = {
  getScenario: () => fetch(`${API_BASE}/scenario`).then(j),
  resetScenario: (body) =>
    fetch(`${API_BASE}/scenario/reset`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  optimize: (body) =>
    fetch(`${API_BASE}/optimize`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  placeHazard: (body) =>
    fetch(`${API_BASE}/chaos/hazard`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  clearHazards: () =>
    fetch(`${API_BASE}/chaos/clear_hazards`, { method: "POST" }).then(j),
  insertIncident: (body) =>
    fetch(`${API_BASE}/insert`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  runArena: (body) =>
    fetch(`${API_BASE}/arena/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j),
  getExplainability: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetch(`${API_BASE}/explainability?${qs}`).then(j);
  },
  scalabilityBenchmark: () => fetch(`${API_BASE}/benchmarks/scalability`).then(j),
  montecarloBenchmark: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetch(`${API_BASE}/benchmarks/montecarlo?${qs}`).then(j);
  },
};

export function connectLiveSocket(onMessage) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/live`);
  ws.onmessage = (evt) => {
    try {
      onMessage(JSON.parse(evt.data));
    } catch (e) {
      console.error("bad ws message", e);
    }
  };
  return ws;
}
