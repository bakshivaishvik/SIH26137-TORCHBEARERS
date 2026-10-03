"""
4/5-Way Algorithm Arena orchestration (Section 5.2): runs Dijkstra/A*,
standard GA, standard PSO, GWO, and QPSO head-to-head on the identical
scenario (same stops, vehicles, edge weights, disruption state) and returns
routes + total cost + convergence time for each, for the split-screen UI.
"""
from __future__ import annotations
import time
import numpy as np
import networkx as nx

from app.optimizer.qpso import QPSOSwarm, QPSOConfig
from app.optimizer.qqpso import QubitQPSOSwarm, QubitQPSOConfig
from app.optimizer.spv import spv_decode_batch
from app.optimizer.split import prins_split
from app.algorithms.pso_ga_gwo import StandardPSO, GeneticAlgorithm, GreyWolfOptimizer, ClassicalConfig
from app.algorithms.dijkstra_astar import dijkstra_shortest_path, astar_shortest_path
from app.core.models import Stop, Vehicle, Depot, ChargingStation


def _make_fitness_fn(stop_ids, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn):
    def fitness_fn(positions: np.ndarray) -> np.ndarray:
        perms = spv_decode_batch(positions)
        out = np.empty(positions.shape[0])
        for i, perm in enumerate(perms):
            tour = [stop_ids[p] for p in perm]
            res = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
            out[i] = res.total_cost if res.feasible else 1e6 + len(tour)
        return out
    return fitness_fn


def run_arena(
    requests: list[Stop],
    vehicles: list[Vehicle],
    depots: list[Depot],
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
    n_agents: int = 40,
    max_iter: int = 120,
    seed: int = 42,
    road_graph: nx.Graph | None = None,
    nearest_depot_node=None,
    nearest_incident_node=None,
) -> dict:
    stops_by_id = {s.id: s for s in requests}
    depots_by_id = {d.id: d for d in depots}
    stop_ids = list(stops_by_id.keys())
    n = len(stop_ids)
    fitness_fn = _make_fitness_fn(stop_ids, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
    cfg = ClassicalConfig(n_agents=n_agents, n_dims=max(n, 1), max_iter=max_iter, seed=seed)
    qcfg = QPSOConfig(n_particles=n_agents, n_dims=max(n, 1), max_iter=max_iter, seed=seed)
    qqcfg = QubitQPSOConfig(n_particles=n_agents, n_dims=max(n, 1), max_iter=max_iter, seed=seed)

    results = {}

    if road_graph is not None and nearest_depot_node is not None and nearest_incident_node is not None:
        t0 = time.perf_counter()
        path, cost = dijkstra_shortest_path(road_graph, nearest_depot_node, nearest_incident_node)
        results["dijkstra"] = {"path": path, "cost": cost, "time_sec": time.perf_counter() - t0, "convergence_history": None}
        t0 = time.perf_counter()
        path, cost = astar_shortest_path(road_graph, nearest_depot_node, nearest_incident_node)
        results["astar"] = {"path": path, "cost": cost, "time_sec": time.perf_counter() - t0, "convergence_history": None}
    else:
        results["dijkstra"] = {"path": None, "cost": None, "time_sec": None,
                                "note": "requires road_graph + endpoints; see graph.osm_graph"}
        results["astar"] = {"path": None, "cost": None, "time_sec": None,
                             "note": "requires road_graph + endpoints; see graph.osm_graph"}

    def run_and_decode(runner, name):
        t0 = time.perf_counter()
        runner.run()
        wall = time.perf_counter() - t0
        best_vec = runner.gbest
        perm = spv_decode_batch(best_vec.reshape(1, -1))[0]
        tour = [stop_ids[p] for p in perm]
        res = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
        return {
            "routes": res.routes if res.feasible else [],
            "feasible": res.feasible,
            "cost": res.total_cost if res.feasible else None,
            "time_sec": wall,
            "convergence_history": runner.convergence_history,
        }

    results["genetic_algorithm"] = run_and_decode(GeneticAlgorithm(cfg, fitness_fn), "ga")
    results["standard_pso"] = run_and_decode(StandardPSO(cfg, fitness_fn), "pso")
    results["gwo"] = run_and_decode(GreyWolfOptimizer(cfg, fitness_fn), "gwo")

    t0 = time.perf_counter()
    swarm = QPSOSwarm(qcfg, fitness_fn)
    swarm.run()
    wall = time.perf_counter() - t0
    perm = spv_decode_batch(swarm.gbest.reshape(1, -1))[0]
    tour = [stop_ids[p] for p in perm]
    res = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
    results["qpso"] = {
        "routes": res.routes if res.feasible else [],
        "feasible": res.feasible,
        "cost": res.total_cost if res.feasible else None,
        "time_sec": wall,
        "convergence_history": swarm.convergence_history,
        "particle_snapshots": [p.tolist() for p in
                               swarm.all_positions_history[::max(1, len(swarm.all_positions_history)//30)]],
    }

    # Qubit-Encoded Quantum PSO (Q-QPSO with R_y rotation gates)
    t0 = time.perf_counter()
    qswarm = QubitQPSOSwarm(qqcfg, fitness_fn)
    qswarm.run()
    wall = time.perf_counter() - t0
    qperm = spv_decode_batch(qswarm.gbest.reshape(1, -1))[0]
    qtour = [stop_ids[p] for p in qperm]
    qres = prins_split(qtour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
    results["qubit_qpso"] = {
        "routes": qres.routes if qres.feasible else [],
        "feasible": qres.feasible,
        "cost": qres.total_cost if qres.feasible else None,
        "time_sec": wall,
        "convergence_history": qswarm.convergence_history,
        "particle_snapshots": [p.tolist() for p in
                               qswarm.all_positions_history[::max(1, len(qswarm.all_positions_history)//30)]],
        "qubit_theta_snapshots": [t.tolist() for t in
                                  qswarm.all_theta_history[::max(1, len(qswarm.all_theta_history)//30)]],
    }

    return results
