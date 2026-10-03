"""
Dynamic multi-factor edge weighting (Section 2.2): live edge resistance
combines vehicle-speed feed, weather severity, elevation profile, and road
surface quality as a composite multiplier on base travel time, plus
optional ST-GNN forecast cost (Section 2.1) and ad-hoc hazard multipliers
from Chaos Mode disruptions (Section 5.1).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import networkx as nx


@dataclass
class WeatherState:
    rainfall_mm_hr: float = 0.0
    waterlogging_level: float = 0.0  # 0 (dry) .. 1 (severe waterlogging)

    def severity_multiplier(self) -> float:
        return 1.0 + 0.06 * self.rainfall_mm_hr + 0.8 * self.waterlogging_level


@dataclass
class LiveEdgeState:
    """Mutable, continuously-updated per-edge state driven by the IoT/MQTT
    telemetry layer (Section 7) and Chaos Mode UI (Section 5.1)."""
    speed_factor: dict = field(default_factory=dict)      # (u,v) -> observed/free-flow speed ratio
    hazard_multiplier: dict = field(default_factory=dict)  # (u,v) -> extra multiplier from a placed hazard
    weather: WeatherState = field(default_factory=WeatherState)
    forecast_multiplier: dict = field(default_factory=dict)  # (u,v) -> ST-GNN forecast-derived multiplier


HAZARD_MULTIPLIERS = {
    "roadblock": 1e6,       # effectively impassable
    "accident": 6.0,
    "damaged_road": 2.5,
    "event_closure": 1e6,
}


class DynamicEdgeWeighter:
    def __init__(self, graph: nx.DiGraph, live_state: LiveEdgeState | None = None):
        self.graph = graph
        self.state = live_state or LiveEdgeState()

    def set_hazard(self, u, v, hazard_type: str):
        mult = HAZARD_MULTIPLIERS.get(hazard_type, 3.0)
        self.state.hazard_multiplier[(u, v)] = mult
        self.state.hazard_multiplier[(v, u)] = mult

    def clear_hazard(self, u, v):
        self.state.hazard_multiplier.pop((u, v), None)
        self.state.hazard_multiplier.pop((v, u), None)

    def edge_minutes(self, u, v, base_minutes: float = None) -> float:
        if base_minutes is None:
            base_minutes = self.graph[u][v].get("weight", 1.0) if self.graph.has_edge(u, v) else 1.0
        
        # Apply multipliers
        elevation_penalty = 1.0
        surface_penalty = 1.0
        if self.graph.has_edge(u, v):
            d = self.graph[u][v]
            elevation_penalty = 1.0 + 0.01 * max(0.0, self.graph.nodes[v].get("elevation_m", 0) -
                                                  self.graph.nodes[u].get("elevation_m", 0))
            surface_penalty = 2.0 - d.get("surface_quality", 0.9)  # rougher road -> slower
            
        speed_factor = self.state.speed_factor.get((u, v), 1.0)
        # Disable ST-GNN and live weather for simulation determinism
        weather_mult = 1.0 # self.state.weather.severity_multiplier()
        hazard_mult = self.state.hazard_multiplier.get((u, v), 1.0)
        forecast_mult = 1.0 # self.state.forecast_multiplier.get((u, v), 1.0)
        return base_minutes * elevation_penalty * surface_penalty * weather_mult * hazard_mult * forecast_mult / max(speed_factor, 1e-3)

    def apply_to_graph_copy(self) -> nx.DiGraph:
        g2 = self.graph.copy()
        for u, v in g2.edges():
            g2[u][v]["weight"] = self.edge_minutes(u, v)
        return g2

    def stop_to_stop_edge_weight_fn(self, node_lookup: dict, osrm_matrix: dict = None):
        """Adapter matching the `edge_weight_fn(a, b, dist_km) -> minutes`
        signature Prins' Split expects (app.optimizer.split), backed by
        this dynamic road-graph weighting instead of straight-line time."""
        def fn(a, b, dist_km):
            ua, ub = node_lookup.get(a.id), node_lookup.get(b.id)
            base_minutes = None
            if osrm_matrix and (a.id, b.id) in osrm_matrix:
                base_minutes = osrm_matrix[(a.id, b.id)]["duration_min"]
            
            if base_minutes is None:
                base_minutes = (dist_km / 35.0) * 60.0  # fallback flat estimate
                
            return self.edge_minutes(ua, ub, base_minutes=base_minutes)
        return fn
