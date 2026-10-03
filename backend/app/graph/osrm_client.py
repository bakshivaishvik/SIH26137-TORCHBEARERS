"""
Client for a locally self-hosted OSRM or GraphHopper instance (Section 7),
used for real distance-matrix computation instead of any external paid API.
Points at the Dockerized service defined in docker-compose.yml
(`osrm` service on localhost:5000 by default). If the local engine is
unreachable, falls back to haversine so the rest of the pipeline degrades
gracefully in dev environments without Docker running.
"""
from __future__ import annotations
import httpx
from app.core.models import Stop, haversine_km

OSRM_BASE_URL = "http://localhost:5000"


class OSRMClient:
    def __init__(self, base_url: str = OSRM_BASE_URL, timeout_sec: float = 3.0):
        self.base_url = base_url
        self.timeout_sec = timeout_sec

    def table(self, stops: list[Stop]) -> dict:
        """Real OSRM /table request for an NxN distance/duration matrix.
        Falls back to a haversine-based matrix if the local OSRM container
        isn't running (e.g., docker-compose not started yet)."""
        coords = ";".join(f"{s.lon},{s.lat}" for s in stops)
        url = f"{self.base_url}/table/v1/driving/{coords}?annotations=distance,duration"
        try:
            resp = httpx.get(url, timeout=self.timeout_sec)
            resp.raise_for_status()
            data = resp.json()
            return {"durations_min": [[d / 60.0 for d in row] for row in data["durations"]],
                     "distances_km": [[d / 1000.0 for d in row] for row in data["distances"]],
                     "source": "osrm"}
        except Exception:
            n = len(stops)
            durations = [[0.0] * n for _ in range(n)]
            distances = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    d = haversine_km(stops[i].lat, stops[i].lon, stops[j].lat, stops[j].lon)
                    distances[i][j] = d
                    durations[i][j] = (d / 35.0) * 60.0
            return {"durations_min": durations, "distances_km": distances, "source": "haversine_fallback"}

    def route(self, a: Stop, b: Stop) -> dict:
        url = f"{self.base_url}/route/v1/driving/{a.lon},{a.lat};{b.lon},{b.lat}?geometries=geojson&overview=full"
        try:
            resp = httpx.get(url, timeout=self.timeout_sec)
            resp.raise_for_status()
            data = resp.json()
            route0 = data["routes"][0]
            return {"geometry": route0["geometry"], "duration_min": route0["duration"] / 60.0,
                    "distance_km": route0["distance"] / 1000.0, "source": "osrm"}
        except Exception:
            dist = haversine_km(a.lat, a.lon, b.lat, b.lon)
            return {"geometry": {"type": "LineString", "coordinates": [[a.lon, a.lat], [b.lon, b.lat]]},
                    "duration_min": (dist / 35.0) * 60.0, "distance_km": dist, "source": "haversine_fallback"}
