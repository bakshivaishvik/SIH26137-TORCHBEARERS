// Frontend-only road snapping for route visualization.
//
// The backend returns straight-line stop-to-stop geometry when it isn't
// running against a live OSRM container (see backend's haversine fallback,
// documented in the repo README). Rather than touching the backend, we
// snap those same waypoints to real streets here in the browser using the
// public OSRM demo routing service (no key, no auth) purely for drawing —
// none of the optimizer's actual cost/time calculations are affected.
const cache = new Map();
const inflight = new Map();

function keyFor(points) {
  return points.map((p) => `${p[0].toFixed(5)},${p[1].toFixed(5)}`).join(";");
}

/**
 * points: ordered array of [lat, lon] waypoints (depot -> stops... -> depot).
 * Returns a road-following [lat, lon][] polyline, or null if snapping
 * isn't possible (caller should fall back to the straight-line points).
 */
export async function snapRouteToRoads(points) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const key = keyFor(points);
  if (cache.has(key)) return cache.get(key);
  if (inflight.has(key)) return inflight.get(key);

  const coordStr = points.map((p) => `${p[1]},${p[0]}`).join(";"); // OSRM wants lon,lat
  const url = `https://router.project-osrm.org/route/v1/driving/${coordStr}?overview=full&geometries=geojson`;

  const promise = fetch(url)
    .then((resp) => {
      if (!resp.ok) throw new Error(`routing HTTP ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      const coords = data?.routes?.[0]?.geometry?.coordinates;
      if (!Array.isArray(coords) || coords.length < 2) throw new Error("no route geometry");
      const snapped = coords.map((c) => [c[1], c[0]]);
      cache.set(key, snapped);
      return snapped;
    })
    .catch(() => {
      cache.set(key, null); // don't hammer the service retrying a route it can't solve
      return null;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, promise);
  return promise;
}
