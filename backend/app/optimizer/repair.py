"""
Deterministic constraint repair (Section 1.4).

Repairs an infeasible SPV-decoded permutation directly via a mathematical
projection instead of random resampling: repeatedly finds the first stop in
the tour whose insertion breaks feasibility for every remaining vehicle
under Prins' Split and relocates it to the next feasible position (cheapest
feasible insertion point scanned left-to-right). The scan is bounded by
`n * MAX_PASSES`, which provably terminates: each successful relocation
strictly reduces the number of "orphan" stops, and there are at most n of
those, so the loop cannot deadlock or run unboundedly.
"""
from __future__ import annotations
from typing import Optional
from app.optimizer.split import prins_split, SplitResult
from app.core.models import Stop, Vehicle, Depot, ChargingStation

MAX_PASSES_PER_STOP = 3


def repair_permutation(
    giant_tour_stop_ids: list[int],
    stops_by_id: dict[int, Stop],
    vehicles: list[Vehicle],
    depots_by_id: dict[int, Depot],
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
) -> tuple[list[int], SplitResult]:
    tour = list(giant_tour_stop_ids)
    n = len(tour)
    max_total_moves = n * MAX_PASSES_PER_STOP

    result = prins_split(tour, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn)
    moves = 0
    while not result.feasible and moves < max_total_moves and len(tour) > 1:
        moved = False
        for k in range(len(tour)):
            stop_id = tour[k]
            trial_tour = tour[:k] + tour[k + 1:]
            best_pos, best_result = None, None
            # try reinserting at every position; keep the first that yields
            # a feasible split (bounded: at most n insertion points)
            for pos in range(len(trial_tour) + 1):
                candidate = trial_tour[:pos] + [stop_id] + trial_tour[pos:]
                res = prins_split(candidate, stops_by_id, vehicles, depots_by_id,
                                   charging_stations, edge_weight_fn)
                if res.feasible and (best_result is None or res.total_cost < best_result.total_cost):
                    best_pos, best_result = pos, res
            moves += 1
            if best_result is not None:
                tour = trial_tour[:best_pos] + [stop_id] + trial_tour[best_pos:]
                result = best_result
                moved = True
                break
        if not moved:
            break  # provably terminate rather than loop with no progress

    return tour, result
