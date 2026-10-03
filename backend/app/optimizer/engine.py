"""
Module boundary (Section 1.8):

    optimize(graph, requests, vehicles, constraints)
        -> {routes, pareto_front, convergence_history}

Fully decoupled from any UI/map library. Wires together:
  QPSO (search) -> SPV (decode) -> Prins' Split (feasibility)
  -> deterministic repair (if infeasible) -> Pareto ranking (multi-objective)
  -> fitness feedback back into the swarm (Section 1.7).

`graph` provides an edge_weight_fn(a: Stop, b: Stop, dist_km) -> minutes,
which is where live congestion / ST-GNN forecasts / weather multipliers
(Section 2.2) get injected without QPSO itself needing to know about them:
when edge weights change, only this callback changes; Prins' Split
re-evaluates the same giant tours at new cost and the swarm naturally
tunnels toward the new hazard-free optimum (Section 1.7 confirmation).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from app.optimizer.qpso import QPSOSwarm, QPSOConfig
from app.optimizer.qqpso import QubitQPSOSwarm, QubitQPSOConfig
from app.optimizer.spv import spv_decode_batch
from app.optimizer.split import prins_split, evaluate_segment
from app.optimizer.repair import repair_permutation
from app.optimizer.pareto import pareto_front as compute_pareto_front
from app.core.models import Stop, Vehicle, Depot, ChargingStation


@dataclass
class OptimizeConstraints:
    n_particles: int = 40
    max_iter: int = 150
    multi_objective: bool = False
    alpha_schedule: str = "nonlinear"
    algorithm_type: str = "delta_qpso"  # "delta_qpso" | "qubit_qpso"
    seed: int | None = None


def optimize(
    graph,                       # object exposing .edge_weight_fn(a, b, dist_km) -> minutes
    requests: list[Stop],
    vehicles: list[Vehicle],
    depots: list[Depot],
    charging_stations: list[ChargingStation] | None = None,
    constraints: OptimizeConstraints | None = None,
) -> dict:
    constraints = constraints or OptimizeConstraints()
    charging_stations = charging_stations or []
    stops_by_id = {s.id: s for s in requests}
    depots_by_id = {d.id: d for d in depots}
    stop_ids = list(stops_by_id.keys())
    n = len(stop_ids)
    edge_weight_fn = getattr(graph, "edge_weight_fn", None)

    def fitness_fn(positions: np.ndarray) -> np.ndarray:
        perms = spv_decode_batch(positions)
        out = np.empty(positions.shape[0])
        for i, perm in enumerate(perms):
            tour = [stop_ids[p] for p in perm]
            res = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
            out[i] = res.total_cost if res.feasible else 1e6 + n
        return out

    if constraints.algorithm_type == "qubit_qpso":
        qcfg = QubitQPSOConfig(n_particles=constraints.n_particles, n_dims=max(n, 1),
                                max_iter=constraints.max_iter, seed=constraints.seed)
        swarm = QubitQPSOSwarm(qcfg, fitness_fn, multi_objective=False)
    else:
        cfg = QPSOConfig(n_particles=constraints.n_particles, n_dims=max(n, 1),
                          max_iter=constraints.max_iter, alpha_schedule=constraints.alpha_schedule,
                          seed=constraints.seed)
        swarm = QPSOSwarm(cfg, fitness_fn, multi_objective=False)
    swarm.run()

    best_perm = spv_decode_batch(swarm.gbest.reshape(1, -1))[0]
    best_tour = [stop_ids[p] for p in best_perm]
    result = prins_split(best_tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)

    if not result.feasible:
        best_tour, result = repair_permutation(best_tour, stops_by_id, vehicles, depots_by_id,
                                                 charging_stations, edge_weight_fn)

    # Build a Pareto front from the swarm's final personal-best population by
    # re-scoring each pBest particle's decoded solution on 4 objectives.
    obj_rows = []
    for i in range(swarm.cfg.n_particles):
        perm = spv_decode_batch(swarm.pbest[i].reshape(1, -1))[0]
        tour = [stop_ids[p] for p in perm]
        res = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
        if res.feasible:
            total_time = sum(r["end_time_min"] for r in res.routes)
            total_penalty = sum(sum(r["penalty_breakdown"].values()) for r in res.routes)
            obj_rows.append([total_time, res.total_cost, total_penalty, len(res.routes)])
    pf = compute_pareto_front(np.array(obj_rows)) if obj_rows else {"points": [], "n_fronts": 0, "pareto_optimal_indices": []}

    return {
        "routes": result.routes if result.feasible else [],
        "feasible": result.feasible,
        "total_cost": result.total_cost if result.feasible else None,
        "pareto_front": pf,
        "convergence_history": swarm.convergence_history,
        "diversity_history": swarm.diversity_history,
        "n_vehicles_used": len(result.routes) if result.feasible else 0,
    }
