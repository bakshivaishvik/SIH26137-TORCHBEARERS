"""
FastAPI backend (Section: Architecture Layer 4 - Interface & Enterprise
Layer), with WebSocket channels for live route/telemetry push to the
frontend. This is the wiring point where a hazard placed in the Chaos Mode
UI flows through edge-weight updates -> localized delta re-optimization ->
explainability log -> back out to every connected client, live.
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.world import world
from app.core.models import Stop, Triage, Vehicle, Depot, ChargingStation
from app.optimizer.engine import optimize, OptimizeConstraints
from app.optimizer.delta_reopt import localized_delta_reopt
from app.optimizer.insertion import insert_new_incident
from app.algorithms.arena import run_arena
from app.explainability.logger import log_decision, query_decisions
from app.integrations.erp_webhook import router as erp_router
from app.benchmarks.profiler import scalability_benchmark, monte_carlo_consistency, ResourceMonitor
from app.benchmarks.solomon_loader import parse_solomon, percent_gap_to_bks
from app.simulation.engine import sim_engine
from app.simulation.scenario import ScenarioParser

app = FastAPI(title="QPSO Ambulance Fleet Router")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(erp_router)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({"type": "snapshot", "data": world.snapshot()})
    try:
        while True:
            await websocket.receive_text()  # keepalive / ignored client pings
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/scenario")
def get_scenario():
    return world.snapshot()


class ResetScenarioBody(BaseModel):
    n_stops: int = 12
    n_vehicles: int = 4
    seed: int = 42


@app.post("/api/scenario/reset")
async def reset_scenario(body: ResetScenarioBody):
    world.reset_demo_scenario(body.n_stops, body.n_vehicles, body.seed)
    await manager.broadcast({"type": "snapshot", "data": world.snapshot()})
    return {"status": "ok"}


class OptimizeBody(BaseModel):
    n_particles: int = 40
    max_iter: int = 150
    seed: Optional[int] = None
    n_vehicles: Optional[int] = None
    algorithm_type: str = "delta_qpso"  # "delta_qpso" | "qubit_qpso"


from app.geometry import route_to_polyline_osrm

def _attach_road_geometry():
    """Annotates world.routes in-place with a `geometry` polyline that
    follows the road graph using OSRM. Also adds total_distance and total_duration."""
    for r in world.routes:
        geom, dist, dur = route_to_polyline_osrm(
            r["stop_sequence"], 
            world.depot, 
            world.stops, 
            world.osrm_client,
            hazards=world.hazards
        )
        r["geometry"] = geom
        r["total_distance"] = dist
        r["total_duration"] = dur


class _GraphAdapter:
    def __init__(self, fn):
        self.edge_weight_fn = fn



@app.post("/api/optimize")
async def run_optimize(body: OptimizeBody):
    with world.lock:
        if body.n_vehicles is not None and body.n_vehicles > 0:
            world.vehicles = [
                Vehicle(id=i, depot_id=0, capacity=4, is_single_patient=False)
                for i in range(body.n_vehicles)
            ]
        stops = list(world.stops.values())
        vehicles = world.vehicles
        depots = [world.depot]
        graph = _GraphAdapter(world.edge_weight_fn())
        result = optimize(graph, stops, vehicles, depots, world.charging_stations,
                            OptimizeConstraints(n_particles=body.n_particles, max_iter=body.max_iter, seed=body.seed, algorithm_type=body.algorithm_type))
        world.routes = result["routes"]
        world.pareto_front = result["pareto_front"]
        world.convergence_history = result["convergence_history"]
        _attach_road_geometry()
        result["routes"] = world.routes

    log_decision("new_request", {"n_stops": len(stops), "n_vehicles": len(vehicles)}, None,
                 None, [r["stop_sequence"] for r in result["routes"]], None, result["total_cost"],
                 f"Full QPSO ({body.algorithm_type}) optimization run over {len(stops)} incidents / {len(vehicles)} vehicles, "
                 f"total cost {result['total_cost']}.")
    await manager.broadcast({"type": "routes_updated", "data": {"routes": world.routes,
                              "convergence_history": world.convergence_history, "pareto_front": world.pareto_front, "algorithm_type": body.algorithm_type}})
    return result


class HazardBody(BaseModel):
    lat: float
    lon: float
    hazard_type: str = "roadblock"  # roadblock | damaged_road | event_closure | accident
    algorithm_type: str = "delta_qpso"  # "delta_qpso" | "qubit_qpso"


@app.post("/api/chaos/hazard")
async def place_hazard(body: HazardBody):
    """Chaos Mode click handler (Section 5.1): maps the click to the
    nearest road-graph edge, applies the hazard multiplier, runs localized
    delta re-optimization on any affected route, logs the decision, and
    broadcasts the update to every connected client -- no manual refresh."""
    with world.lock:
        u = world._nearest_node(body.lat, body.lon)
        neighbors = list(world.road_graph[u].keys())
        if not neighbors:
            return {"status": "no_edge_found"}
        v = neighbors[0]
        world.weighter.set_hazard(u, v, body.hazard_type)
        world.hazards.append({"lat": body.lat, "lon": body.lon, "type": body.hazard_type})

        # Find affected route and hazard_edge
        hazard_stop_ids = [sid for sid, node in world.node_lookup.items() if node in (u, v)]
        hazard_edge = tuple(hazard_stop_ids[:2]) if len(hazard_stop_ids) >= 2 else (
            hazard_stop_ids[0], hazard_stop_ids[0]) if hazard_stop_ids else (None, None)

        # If no stop node directly matched, find route whose geometry or stops pass closest to (lat, lon)
        if hazard_edge[0] is None and world.routes:
            best_route = None
            best_dist = float("inf")
            best_stop_id = None
            for r in world.routes:
                geom = r.get("geometry", [])
                for pt in geom:
                    d = (pt[0] - body.lat) ** 2 + (pt[1] - body.lon) ** 2
                    if d < best_dist:
                        best_dist = d
                        best_route = r
                        if r.get("stop_sequence"):
                            best_stop_id = r["stop_sequence"][0]
                # Also check each stop in the route
                for sid in r.get("stop_sequence", []):
                    s = world.stops.get(sid)
                    if s:
                        d = (s.lat - body.lat) ** 2 + (s.lon - body.lon) ** 2
                        if d < best_dist:
                            best_dist = d
                            best_route = r
                            best_stop_id = sid

            if best_route and best_stop_id is not None:
                hazard_edge = (best_stop_id, best_stop_id)

        routes_before = [dict(r) for r in world.routes]
        if hazard_edge[0] is not None and world.routes:
            out = localized_delta_reopt(
                world.routes, hazard_edge, world.stops_by_id(), world.vehicles, world.depots_by_id(),
                world.charging_stations, world.edge_weight_fn(), local_iters=25, local_particles=16,
                algorithm_type=body.algorithm_type,
            )
            world.routes = out["routes"]
            wall_clock = out["wall_clock_sec"]
            reopt_ids = out["reoptimized_route_ids"]
            _attach_road_geometry()
            for r in world.routes:
                if r["vehicle_id"] in reopt_ids:
                    r["is_rerouted"] = True
        else:
            wall_clock, reopt_ids = 0.0, []

    cost_before = sum(r.get("cost", 0) for r in routes_before)
    cost_after = sum(r.get("cost", 0) for r in world.routes)
    log_decision("hazard", {"lat": body.lat, "lon": body.lon, "type": body.hazard_type, "edge": [u, v]},
                 reopt_ids[0] if reopt_ids else None,
                 [r["stop_sequence"] for r in routes_before], [r["stop_sequence"] for r in world.routes],
                 cost_before, cost_after,
                 f"{body.hazard_type} placed near ({body.lat:.4f},{body.lon:.4f}); "
                 f"{len(reopt_ids)} route(s) re-optimized in {wall_clock:.3f}s, cost {cost_before:.1f}->{cost_after:.1f}.")

    await manager.broadcast({"type": "hazard_reroute", "data": {
        "hazard": {"lat": body.lat, "lon": body.lon, "type": body.hazard_type, "edge": [u, v]},
        "hazards": world.hazards,
        "routes": world.routes, 
        "routes_before": routes_before,
        "reoptimized_route_ids": reopt_ids, 
        "wall_clock_sec": wall_clock,
    }})
    return {"status": "ok", "reoptimized_route_ids": reopt_ids, "wall_clock_sec": wall_clock, "routes": world.routes, "routes_before": routes_before}


@app.post("/api/chaos/clear_hazards")
async def clear_hazards():
    with world.lock:
        world.weighter.state.hazard_multiplier.clear()
        world.hazards.clear()
        for r in world.routes:
            r.pop("is_rerouted", None)
        if world.routes:
            _attach_road_geometry()
    await manager.broadcast({
        "type": "hazards_cleared",
        "data": {"routes": world.routes, "hazards": [], "routes_before": []}
    })
    return {"status": "ok", "routes": world.routes, "hazards": []}


class InsertIncidentBody(BaseModel):
    lat: float
    lon: float
    triage: str = "URGENT"
    sla_response_min: float = 30.0


@app.post("/api/insert")
async def insert_incident(body: InsertIncidentBody):
    with world.lock:
        new_id = world._next_stop_id
        world._next_stop_id += 1
        new_stop = Stop(id=new_id, lat=body.lat, lon=body.lon, sla_response_min=body.sla_response_min,
                          triage=Triage[body.triage] if body.triage in Triage.__members__ else Triage.URGENT,
                          tw_start_min=0, tw_hard_end_min=600, tw_soft_end_min=90)
        world.stops[new_id] = new_stop
        world.node_lookup[new_id] = world._nearest_node(body.lat, body.lon)
        world._refresh_osrm_cache()

        result = insert_new_incident(world.routes, new_stop, world.stops_by_id(), world.vehicles,
                                       world.depots_by_id(), world.charging_stations, world.edge_weight_fn())
        routes_before = world.routes
        if result["success"]:
            world.routes = result["routes"]
            _attach_road_geometry()

    log_decision("insertion", {"lat": body.lat, "lon": body.lon, "triage": body.triage}, result.get("vehicle_id"),
                 [r["stop_sequence"] for r in routes_before], [r["stop_sequence"] for r in world.routes],
                 None, result.get("marginal_cost"),
                 f"New incident #{new_id} ({body.triage}) inserted via {result['strategy']} "
                 f"on vehicle {result.get('vehicle_id')}, marginal cost {result.get('marginal_cost')}.")

    await manager.broadcast({"type": "incident_inserted", "data": {"new_stop_id": new_id, "result": result}})
    return result

# --- Simulation Endpoints ---

def _sim_payload():
    return {
        "tick": sim_engine.tick,
        "static_world": sim_engine.static_world.snapshot(),
        "dynamic_world": sim_engine.dynamic_world.snapshot(),
        "metrics": sim_engine.get_metrics(),
    }

@app.websocket("/ws/sim")
async def ws_sim(websocket: WebSocket):
    await manager.connect(websocket)
    await websocket.send_json({
        "type": "sim_snapshot", 
        "data": _sim_payload()
    })
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

class SimScenarioBody(BaseModel):
    scenario: dict

@app.post("/api/simulation/load")
async def sim_load(body: SimScenarioBody):
    sim_engine.load_scenario(body.scenario)
    await manager.broadcast({
        "type": "sim_snapshot", 
        "data": _sim_payload()
    })
    return {"status": "loaded", "data": _sim_payload()}

class SimOrderBody(BaseModel):
    pickup_lat: float
    pickup_lon: float
    dropoff_lat: float
    dropoff_lon: float

@app.post("/api/simulation/order")
async def sim_add_order(body: SimOrderBody):
    sim_engine.add_custom_order(body.pickup_lat, body.pickup_lon, body.dropoff_lat, body.dropoff_lon)
    await manager.broadcast({
        "type": "sim_snapshot", 
        "data": _sim_payload()
    })
    return {"status": "order_added", "data": _sim_payload()}

@app.post("/api/simulation/reset")
async def sim_reset():
    sim_engine.reset()
    await manager.broadcast({
        "type": "sim_snapshot", 
        "data": _sim_payload()
    })
    return {"status": "reset", "data": _sim_payload()}

@app.get("/api/simulation/scenario/generate")
async def sim_generate_scenario(num_orders: int = 6, num_partners: int = 3, seed: int = 42):
    scenario = ScenarioParser.generate_random_scenario(seed=seed, num_orders=num_orders, num_partners=num_partners)
    sim_engine.load_scenario(scenario)
    await manager.broadcast({
        "type": "sim_snapshot", 
        "data": _sim_payload()
    })
    return {"status": "generated", "scenario": scenario, "data": _sim_payload()}

class SimStateBody(BaseModel):
    running: bool

@app.post("/api/simulation/state")
async def sim_state(body: SimStateBody):
    sim_engine.running = body.running
    return {"status": "ok", "running": sim_engine.running}

@app.post("/api/simulation/tick")
async def sim_tick():
    sim_engine.advance_tick()
    await manager.broadcast({
        "type": "sim_tick", 
        "data": _sim_payload()
    })
    return {"status": "ok", "tick": sim_engine.tick, "data": _sim_payload()}

@app.post("/api/simulation/hazard")
async def sim_hazard(body: dict):
    disruption = {
        "lat": body["lat"],
        "lon": body["lon"],
        "type": body.get("type", "roadblock"),
        "trigger_tick": sim_engine.tick
    }
    sim_engine.inject_disruption(disruption)
    await manager.broadcast({
        "type": "sim_tick", 
        "data": _sim_payload()
    })
    return {"status": "ok", "data": _sim_payload()}

@app.get("/api/simulation/export")
def sim_export():
    return sim_engine.get_metrics()

class ArenaBody(BaseModel):
    n_agents: int = 30
    max_iter: int = 80
    seed: int = 1


@app.post("/api/arena/run")
def arena_run(body: ArenaBody):
    with world.lock:
        stops = list(world.stops.values())
        vehicles = world.vehicles
        node0 = world._nearest_node(world.depot.lat, world.depot.lon)
        target_stop = stops[0] if stops else None
        node1 = world._nearest_node(target_stop.lat, target_stop.lon) if target_stop else node0
        results = run_arena(stops, vehicles, [world.depot], world.charging_stations, world.edge_weight_fn(),
                              n_agents=body.n_agents, max_iter=body.max_iter, seed=body.seed,
                              road_graph=world.road_graph, nearest_depot_node=node0, nearest_incident_node=node1)
    return results


@app.get("/api/explainability")
def get_explainability(vehicle_id: Optional[int] = None, event_type: Optional[str] = None, limit: int = 50):
    return query_decisions(vehicle_id=vehicle_id, event_type=event_type, limit=limit)


@app.get("/api/benchmarks/scalability")
def benchmarks_scalability():
    return scalability_benchmark(node_counts=(10, 20, 40), max_iter=40, n_particles=20)


@app.get("/api/benchmarks/montecarlo")
def benchmarks_montecarlo(n_stops: int = 10, n_vehicles: int = 3, n_seeds: int = 5):
    return monte_carlo_consistency(n_stops=n_stops, n_vehicles=n_vehicles, n_seeds=n_seeds, max_iter=40, n_particles=20)


@app.post("/api/benchmarks/solomon")
def benchmarks_solomon(path: str):
    inst = parse_solomon(path)
    graph = _GraphAdapter(None)
    result = optimize(graph, inst["stops"], inst["vehicles"], [inst["depot"]], [],
                        OptimizeConstraints(n_particles=30, max_iter=100))
    gap = percent_gap_to_bks(inst["name"], result["total_cost"]) if result["feasible"] else None
    return {"instance": inst["name"], "feasible": result["feasible"], "cost": result["total_cost"], "pct_gap_to_bks": gap}


class CopilotBody(BaseModel):
    question: str


@app.post("/api/copilot/ask")
def copilot_ask(body: CopilotBody):
    import os
    if not os.environ.get("GROQ_API_KEY"):
        return {"answer": None, "detail": "GROQ_API_KEY is not set on the backend. Export it to enable "
                 "the GenAI Dispatcher Copilot (see app/integrations/groq_copilot.py)."}
    from app.integrations.groq_copilot import DispatcherCopilot
    copilot = DispatcherCopilot(live_state_provider=lambda: world.snapshot())
    return {"answer": copilot.ask(body.question)}


@app.get("/health")
def health():
    return {"status": "ok", "ts": time.time()}
