"""
NSGA-II-style non-dominated sorting + crowding distance (Section 1.6),
applied over the swarm's fitness vectors: [travel_time, distance, energy,
penalty(late+SLA+overtime)]. Produces the Pareto front the frontend's
profiler dashboard renders, rather than a single scalarized best.
"""
from __future__ import annotations
import numpy as np


def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.all(a <= b) and np.any(a < b))


def fast_non_dominated_sort(objective_matrix: np.ndarray) -> list[list[int]]:
    n = objective_matrix.shape[0]
    S = [[] for _ in range(n)]
    dom_count = np.zeros(n, dtype=int)
    fronts: list[list[int]] = [[]]

    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(objective_matrix[p], objective_matrix[q]):
                S[p].append(q)
            elif dominates(objective_matrix[q], objective_matrix[p]):
                dom_count[p] += 1
        if dom_count[p] == 0:
            fronts[0].append(p)

    i = 0
    while fronts[i]:
        next_front = []
        for p in fronts[i]:
            for q in S[p]:
                dom_count[q] -= 1
                if dom_count[q] == 0:
                    next_front.append(q)
        i += 1
        fronts.append(next_front)
    fronts.pop()  # trailing empty front
    return fronts


def crowding_distance(objective_matrix: np.ndarray, front: list[int]) -> dict[int, float]:
    if not front:
        return {}
    m = objective_matrix.shape[1]
    dist = {i: 0.0 for i in front}
    for obj_idx in range(m):
        vals = sorted(front, key=lambda i: objective_matrix[i, obj_idx])
        dist[vals[0]] = dist[vals[-1]] = float("inf")
        obj_min = objective_matrix[vals[0], obj_idx]
        obj_max = objective_matrix[vals[-1], obj_idx]
        span = obj_max - obj_min
        if span <= 1e-12:
            continue
        for k in range(1, len(vals) - 1):
            prev_v = objective_matrix[vals[k - 1], obj_idx]
            next_v = objective_matrix[vals[k + 1], obj_idx]
            dist[vals[k]] += (next_v - prev_v) / span
    return dist


def pareto_front(objective_matrix: np.ndarray) -> dict:
    """Returns front indices ranked (front 0 = true Pareto front) plus
    crowding distances, ready for the UI to render a scatter/parallel-coords
    chart of the trade-off surface."""
    fronts = fast_non_dominated_sort(objective_matrix)
    out = []
    for rank, front in enumerate(fronts):
        cd = crowding_distance(objective_matrix, front)
        for idx in front:
            out.append({
                "index": int(idx),
                "rank": rank,
                "crowding_distance": cd[idx] if np.isfinite(cd[idx]) else None,
                "objectives": objective_matrix[idx].tolist(),
            })
    return {"points": out, "n_fronts": len(fronts), "pareto_optimal_indices": fronts[0] if fronts else []}
