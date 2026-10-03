"""
Localized delta re-optimization (Section 1.5).

When a live disruption (hazard/closure/accident) invalidates one or more
sub-tours, we do NOT recompute the whole global solution. We isolate the
affected sub-tour(s) — any route whose stop sequence touches the disrupted
edge, or whose cost changed materially because a hazard sits on its path —
as an independent subgraph, run a small bounded number of QPSO iterations
scoped only to that subgraph's stop set, then splice the repaired sub-tour
back in place. This targets sub-second/low-second wall clock on
city-block-sized disruptions because the search space is O(stops in the
broken route), not O(all stops in the city).
"""
from __future__ import annotations
import time
import numpy as np

from app.optimizer.qpso import QPSOSwarm, QPSOConfig
from app.optimizer.qqpso import QubitQPSOSwarm, QubitQPSOConfig
from app.optimizer.spv import spv_decode_batch
from app.optimizer.split import prins_split
from app.core.models import Stop, Vehicle, Depot, ChargingStation


def route_touches_hazard(route: dict, hazard_edge: tuple[int, int]) -> bool:
    seq = route["stop_sequence"]
    edges = list(zip(seq[:-1], seq[1:]))
    a, b = hazard_edge
    return (a, b) in edges or (b, a) in edges or a in seq or b in seq


def localized_delta_reopt(
    full_routes: list[dict],
    hazard_edge: tuple[int, int],
    stops_by_id: dict[int, Stop],
    vehicles: list[Vehicle],
    depots_by_id: dict[int, Depot],
    charging_stations: list[ChargingStation],
    new_edge_weight_fn,
    local_iters: int = 25,
    local_particles: int = 16,
    algorithm_type: str = "delta_qpso",
) -> dict:
    t0 = time.perf_counter()
    affected = [r for r in full_routes if route_touches_hazard(r, hazard_edge)]
    unaffected = [r for r in full_routes if r not in affected]

    if not affected:
        return {"routes": full_routes, "reoptimized_route_ids": [], "wall_clock_sec": 0.0}

    affected_vehicle_ids = {r["vehicle_id"] for r in affected}
    local_vehicles = [v for v in vehicles if v.id in affected_vehicle_ids]
    local_stop_ids = [sid for r in affected for sid in r["stop_sequence"]]
    n_dims = len(local_stop_ids)

    def fitness_fn(positions: np.ndarray) -> np.ndarray:
        perms = spv_decode_batch(positions)
        out = np.empty(positions.shape[0])
        for i, perm in enumerate(perms):
            tour = [local_stop_ids[p] for p in perm]
            res = prins_split(tour, stops_by_id, local_vehicles, depots_by_id,
                               charging_stations, new_edge_weight_fn)
            out[i] = res.total_cost if res.feasible else 1e6 + len(tour)
        return out

    if algorithm_type == "qubit_qpso":
        qcfg = QubitQPSOConfig(n_particles=local_particles, n_dims=max(n_dims, 1), max_iter=local_iters)
        swarm = QubitQPSOSwarm(qcfg, fitness_fn)
    else:
        cfg = QPSOConfig(n_particles=local_particles, n_dims=max(n_dims, 1),
                          max_iter=local_iters, alpha_schedule="nonlinear")
        swarm = QPSOSwarm(cfg, fitness_fn)
    swarm.run()

    best_perm = spv_decode_batch(swarm.gbest.reshape(1, -1))[0]
    best_tour = [local_stop_ids[p] for p in best_perm]
    repaired = prins_split(best_tour, stops_by_id, local_vehicles, depots_by_id,
                            charging_stations, new_edge_weight_fn)

    wall = time.perf_counter() - t0
    new_full = unaffected + (repaired.routes if repaired.feasible else affected)
    return {
        "routes": new_full,
        "reoptimized_route_ids": [r["vehicle_id"] for r in affected],
        "wall_clock_sec": wall,
        "feasible": repaired.feasible,
        "convergence_history": swarm.convergence_history,
    }
