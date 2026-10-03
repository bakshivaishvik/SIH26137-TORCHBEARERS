"""
Dynamic on-the-fly order insertion (Section 4.2).

Supports inserting a new high-priority incident into active routes at any
time: computes the minimal-cost insertion point across the current fleet
(trying every position in every existing route, plus a brand-new
single-stop route if no existing slot is feasible) with zero violation of
existing hard delivery/time-window constraints, and returns the updated
route set ready for immediate re-dispatch.
"""
from __future__ import annotations
from app.optimizer.split import prins_split, evaluate_segment
from app.core.models import Stop, Vehicle, Depot, ChargingStation

BIG = float("inf")


def insert_new_incident(
    current_routes: list[dict],
    new_stop: Stop,
    stops_by_id: dict[int, Stop],
    vehicles: list[Vehicle],
    depots_by_id: dict[int, Depot],
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
) -> dict:
    stops_by_id = dict(stops_by_id)
    stops_by_id[new_stop.id] = new_stop
    vehicles_by_id = {v.id: v for v in vehicles}

    best = None  # (new_cost_for_route, route_index, new_stop_sequence, position)

    for r_idx, route in enumerate(current_routes):
        vehicle = vehicles_by_id.get(route["vehicle_id"])
        if vehicle is None:
            continue
        depot = depots_by_id[route["depot_id"]]
        seq_ids = route["stop_sequence"]
        for pos in range(len(seq_ids) + 1):
            candidate_ids = seq_ids[:pos] + [new_stop.id] + seq_ids[pos:]
            candidate_stops = [stops_by_id[i] for i in candidate_ids]
            ev = evaluate_segment(candidate_stops, vehicle, depot, charging_stations, edge_weight_fn)
            if not ev.feasible:
                continue
            marginal_cost = ev.cost - route["cost"]
            if best is None or marginal_cost < best[0]:
                best = (marginal_cost, r_idx, candidate_ids, pos, ev)

    if best is not None:
        marginal_cost, r_idx, candidate_ids, pos, ev = best
        new_routes = [dict(r) for r in current_routes]
        new_routes[r_idx] = {
            **new_routes[r_idx],
            "stop_sequence": candidate_ids,
            "cost": ev.cost,
            "end_time_min": ev.end_time_min,
            "end_soc_frac": ev.end_soc_frac,
            "inserted_charging_stops": ev.inserted_charging_stops,
            "penalty_breakdown": ev.penalty_breakdown,
        }
        return {
            "success": True, "strategy": "insert_into_existing_route",
            "vehicle_id": new_routes[r_idx]["vehicle_id"], "marginal_cost": marginal_cost,
            "routes": new_routes,
        }

    # No feasible slot in any existing route -> dispatch a fresh vehicle if one is idle
    used_vehicle_ids = {r["vehicle_id"] for r in current_routes}
    idle_vehicles = [v for v in vehicles if v.id not in used_vehicle_ids]
    for v in idle_vehicles:
        depot = depots_by_id[v.depot_id]
        ev = evaluate_segment([new_stop], v, depot, charging_stations, edge_weight_fn)
        if ev.feasible:
            new_routes = current_routes + [{
                "vehicle_id": v.id, "depot_id": depot.id, "stop_sequence": [new_stop.id],
                "cost": ev.cost, "end_time_min": ev.end_time_min, "end_soc_frac": ev.end_soc_frac,
                "inserted_charging_stops": ev.inserted_charging_stops,
                "penalty_breakdown": ev.penalty_breakdown,
            }]
            return {"success": True, "strategy": "dispatch_new_vehicle", "vehicle_id": v.id,
                     "marginal_cost": ev.cost, "routes": new_routes}

    return {"success": False, "strategy": "none", "reason": "no feasible slot or idle vehicle",
             "routes": current_routes}
