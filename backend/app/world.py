"""
In-memory live world state for the FastAPI backend: current stops,
vehicles, depots, road graph, dynamic edge weighter, and the last computed
route set. This is the single source of truth the REST endpoints and
WebSocket broadcaster both read/write, standing in for a real datastore
(swap for Postgres/Redis in production without touching the optimizer).
"""
from __future__ import annotations
import threading
import numpy as np

from app.core.models import Stop, Vehicle, Depot, ChargingStation, Triage
from app.graph.osm_graph import load_osm_graph, synthetic_city_grid
from app.graph.edge_weights import DynamicEdgeWeighter


class World:
    def __init__(self):
        self.lock = threading.RLock()
        self.depot = Depot(id=0, lat=12.9716, lon=77.5946)
        self.vehicles: list[Vehicle] = []
        self.stops: dict[int, Stop] = {}
        self.charging_stations: list[ChargingStation] = []
        self.routes: list[dict] = []
        self.pareto_front: dict = {}
        self.convergence_history: list[float] = []
        # Keep synthetic_city_grid as an explicit fallback inside load_osm_graph
        self.road_graph = load_osm_graph(bbox=(13.0, 12.9, 77.7, 77.5))
        self.weighter = DynamicEdgeWeighter(self.road_graph)
        self.node_lookup: dict[int, int] = {}   # stop_id -> nearest road-graph node
        self._next_stop_id = 1000
        from app.graph.osrm_client import OSRMClient
        import os
        osrm_url = os.environ.get("OSRM_BASE_URL", "http://osrm:5000")
        self.osrm_client = OSRMClient(osrm_url)
        self.osrm_matrix_cache = {} # Map (a.id, b.id) to {duration, distance}
        self.hazards: list[dict] = []
        self.reset_demo_scenario()

    def _nearest_node(self, lat: float, lon: float) -> int:
        best, best_d = None, float("inf")
        for n, d in self.road_graph.nodes(data=True):
            dd = (d["lat"] - lat) ** 2 + (d["lon"] - lon) ** 2
            if dd < best_d:
                best, best_d = n, dd
        return best

    def _refresh_osrm_cache(self):
        all_points = [Stop(id=self.depot.id, lat=self.depot.lat, lon=self.depot.lon, demand=0, tw_start_min=0, tw_hard_end_min=0, tw_soft_end_min=0, sla_response_min=0, triage=Triage.STANDARD)]
        for s in self.stops.values():
            all_points.append(s)
        for cs in self.charging_stations:
            all_points.append(Stop(id=-cs.id, lat=cs.lat, lon=cs.lon, demand=0, tw_start_min=0, tw_hard_end_min=0, tw_soft_end_min=0, sla_response_min=0, triage=Triage.STANDARD))
        
        matrix = self.osrm_client.table(all_points)
        self.osrm_matrix_cache.clear()
        
        for i, a in enumerate(all_points):
            for j, b in enumerate(all_points):
                if i == j: continue
                self.osrm_matrix_cache[(a.id, b.id)] = {
                    "duration_min": matrix["durations_min"][i][j],
                    "distance_km": matrix["distances_km"][i][j]
                }

    def reset_demo_scenario(self, n_stops: int = 12, n_vehicles: int = 4, seed: int = 42):
        with self.lock:
            rng = np.random.default_rng(seed)
            self.vehicles = [Vehicle(id=i, depot_id=0, capacity=4, is_single_patient=False)
                              for i in range(n_vehicles)]
            self.stops = {}
            for i in range(n_stops):
                lat = self.depot.lat + rng.uniform(-0.03, 0.03)
                lon = self.depot.lon + rng.uniform(-0.03, 0.03)
                triage = rng.choice(list(Triage))
                sid = 1 + i
                self.stops[sid] = Stop(
                    id=sid, lat=lat, lon=lon, demand=1,
                    tw_start_min=0, tw_hard_end_min=600, tw_soft_end_min=180,
                    sla_response_min=45, triage=Triage(triage),
                )
            self.charging_stations = [ChargingStation(id=1, lat=self.depot.lat + 0.01, lon=self.depot.lon + 0.01)]
            for sid, s in self.stops.items():
                self.node_lookup[sid] = self._nearest_node(s.lat, s.lon)
            self.routes = []
            self.pareto_front = {}
            self.convergence_history = []
            self.hazards.clear()
            self.weighter.state.hazard_multiplier.clear()
            self._refresh_osrm_cache()

    def edge_weight_fn(self):
        return self.weighter.stop_to_stop_edge_weight_fn(self.node_lookup, self.osrm_matrix_cache)

    def stops_by_id(self) -> dict[int, Stop]:
        return self.stops

    def depots_by_id(self) -> dict[int, Depot]:
        return {self.depot.id: self.depot}

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "depot": self.depot.__dict__,
                "vehicles": [v.__dict__ for v in self.vehicles],
                "stops": [s.__dict__ for s in self.stops.values()],
                "charging_stations": [c.__dict__ for c in self.charging_stations],
                "routes": self.routes,
                "pareto_front": self.pareto_front,
                "convergence_history": self.convergence_history,
                "hazards": list(self.hazards),
            }


world = World()
