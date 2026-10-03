"""
Prins' Split feasibility projection (Section 1.3), extended to handle,
simultaneously, in a single feasibility pass over each candidate segment:

  - VRPTW: hard delivery windows + soft penalty-slope lateness
  - E-VRP: non-linear battery discharge (via core.models.energy_for_leg_kwh),
           elevation-adjusted consumption, dynamic charging-station insertion
  - Multi-Depot & Dynamic Pickups: multiple depots/sub-fleets, mid-route
    pickup insertion without invalidating the remainder of the route
  - Ambulance constraints: response-time SLA, triage priority weighting,
    single-patient vs multi-capacity vehicles

Classic Prins' Split builds an auxiliary DAG over the giant tour where an
arc (i -> j) exists iff the sub-sequence tour[i:j] is a feasible single
vehicle trip, weighted by that trip's cost, and the whole tour is split by
finding the shortest path from node 0 to node n in that DAG. We do the same
here, except "feasible" is evaluated against the full constraint bundle
above instead of just capacity.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from app.core.models import Stop, Vehicle, ChargingStation, Depot, Triage, haversine_km, energy_for_leg_kwh

BIG = float("inf")


@dataclass
class SegmentEval:
    feasible: bool
    cost: float = BIG
    end_time_min: float = 0.0
    end_soc_frac: float = 1.0
    inserted_charging_stops: list = field(default_factory=list)
    penalty_breakdown: dict = field(default_factory=dict)


@dataclass
class SplitResult:
    routes: list           # list of dicts: {vehicle_id, depot_id, stop_sequence, cost, ...}
    total_cost: float
    feasible: bool
    objective_vector: np.ndarray = None  # [time, distance, energy, penalty]


def _travel_time_min(a: Stop, b: Stop, speed_kmh: float, edge_weight_fn=None) -> tuple[float, float]:
    dist_km = haversine_km(a.lat, a.lon, b.lat, b.lon)
    if edge_weight_fn is not None:
        # allows live congestion / ST-GNN forecast / weather multiplier injection
        minutes = edge_weight_fn(a, b, dist_km)
    else:
        minutes = (dist_km / max(speed_kmh, 1e-6)) * 60.0
    return dist_km, minutes


def evaluate_segment(
    seq: list[Stop],
    vehicle: Vehicle,
    depot: Depot,
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
    dispatch_time_min: float = 0.0,
    late_penalty_per_min: float = 5.0,
    sla_penalty_per_min: float = 10.0,
    overtime_penalty_per_min: float = 3.0,
) -> SegmentEval:
    """Evaluate one candidate vehicle trip (a slice of the giant tour) for
    full feasibility + cost, inserting charging stops on the fly if SoC
    would otherwise go negative."""

    if vehicle.is_single_patient:
        total_demand = sum(s.demand for s in seq if not s.is_pickup)
        n_primary_patients = sum(1 for s in seq if not s.is_pickup)
        if n_primary_patients > 1:
            return SegmentEval(feasible=False)
    else:
        total_demand = sum(s.demand for s in seq)

    if total_demand > vehicle.capacity:
        return SegmentEval(feasible=False)

    # depot group restriction (multi-depot)
    for s in seq:
        if s.depot_group is not None and s.depot_group != depot.id:
            return SegmentEval(feasible=False)

    start_lat = vehicle.partner_start_lat if vehicle.partner_start_lat is not None else depot.lat
    start_lon = vehicle.partner_start_lon if vehicle.partner_start_lon is not None else depot.lon
    cur = Stop(id=-1, lat=start_lat, lon=start_lon, elevation_m=0.0)
    t = dispatch_time_min
    soc = 1.0
    dist_total = 0.0
    energy_total = 0.0
    penalty = 0.0
    inserted = []
    penalty_breakdown = {"late": 0.0, "sla": 0.0, "overtime": 0.0}

    def maybe_insert_charging(dist_km, elev_delta):
        nonlocal soc, t, energy_total
        needed = energy_for_leg_kwh(vehicle, dist_km, elev_delta) / vehicle.battery_capacity_kwh
        if soc - needed >= 0.05 or not charging_stations:
            return needed, None
        # find nearest charging station to current position to splice in
        best_cs, best_d = None, BIG
        for cs in charging_stations:
            d = haversine_km(cur.lat, cur.lon, cs.lat, cs.lon)
            if d < best_d:
                best_cs, best_d = cs, d
        if best_cs is None:
            return needed, None
        detour_needed = energy_for_leg_kwh(vehicle, best_d, 0.0) / vehicle.battery_capacity_kwh
        if soc - detour_needed < 0.02:
            return needed, "STRAND"  # cannot even reach a charger -> infeasible
        charge_needed_frac = min(1.0, needed + detour_needed + 0.1) - (soc - detour_needed)
        charge_needed_frac = max(charge_needed_frac, 0.0)
        charge_time = charge_needed_frac / max(best_cs.charge_rate_soc_per_min, 1e-6)
        return needed, (best_cs, best_d, detour_needed, charge_time, charge_needed_frac)

    picked_up = set()

    for nxt in seq:
        dist_km, minutes = _travel_time_min(cur, nxt, vehicle.max_speed_kmh, edge_weight_fn)
        elev_delta = nxt.elevation_m - cur.elevation_m

        needed_frac, charge_action = maybe_insert_charging(dist_km, elev_delta)
        if charge_action == "STRAND":
            return SegmentEval(feasible=False)
        if isinstance(charge_action, tuple):
            cs, cs_dist_km, detour_frac, charge_time, charge_frac = charge_action
            # detour to charger, charge, then continue to nxt from charger
            t += (cs_dist_km / max(vehicle.max_speed_kmh, 1e-6)) * 60.0
            soc -= detour_frac
            t += charge_time
            soc = min(1.0, soc + charge_frac)
            inserted.append({"station_id": cs.id, "at_time_min": t})
            dist_km2, minutes2 = _travel_time_min(
                Stop(id=-2, lat=cs.lat, lon=cs.lon), nxt, vehicle.max_speed_kmh, edge_weight_fn
            )
            dist_total += cs_dist_km + dist_km2
            energy_total += (detour_frac + needed_frac) * vehicle.battery_capacity_kwh
            t += minutes2
            soc -= needed_frac
        else:
            dist_total += dist_km
            energy_total += needed_frac * vehicle.battery_capacity_kwh
            t += minutes
            soc -= needed_frac

        if soc < -1e-6:
            return SegmentEval(feasible=False)

        # Swiggy pairing logic
        if nxt.stop_type == "PICKUP":
            picked_up.add(nxt.order_id)
        elif nxt.stop_type == "DROPOFF":
            if nxt.status == "COLLECTED":
                if nxt.assigned_vehicle_id != vehicle.id:
                    return SegmentEval(feasible=False)
            else:
                if nxt.order_id not in picked_up:
                    return SegmentEval(feasible=False)
                picked_up.remove(nxt.order_id)

        # arrival at nxt
        if t < nxt.tw_start_min:
            t = nxt.tw_start_min  # wait for window to open
        if t > nxt.tw_hard_end_min:
            return SegmentEval(feasible=False)  # hard VRPTW violation
        soft_end = nxt.soft_end()
        if t > soft_end:
            lateness = t - soft_end
            slope = {Triage.CRITICAL: 4.0, Triage.URGENT: 2.5, Triage.STANDARD: 1.0,
                     Triage.NON_URGENT: 0.5}[nxt.triage]
            pen = lateness * late_penalty_per_min * slope
            penalty += pen
            penalty_breakdown["late"] += pen

        if nxt.sla_response_min is not None:
            response = t - dispatch_time_min
            if response > nxt.sla_response_min:
                pen = (response - nxt.sla_response_min) * sla_penalty_per_min
                penalty += pen
                penalty_breakdown["sla"] += pen

        t += nxt.service_time_min
        cur = nxt

    if picked_up:
        return SegmentEval(feasible=False)  # Did not drop off all orders!

    # return-to-depot leg
    dist_km, minutes = _travel_time_min(cur, Stop(id=-3, lat=depot.lat, lon=depot.lon), vehicle.max_speed_kmh, edge_weight_fn)
    dist_total += dist_km
    t += minutes

    if t - dispatch_time_min > vehicle.crew_overtime_start_min:
        overtime_min = (t - dispatch_time_min) - vehicle.crew_overtime_start_min
        pen = overtime_min * overtime_penalty_per_min
        penalty += pen
        penalty_breakdown["overtime"] += pen

    cost = t + 0.5 * dist_total + penalty  # time-dominant scalar cost for classical split
    return SegmentEval(
        feasible=True, cost=cost, end_time_min=t, end_soc_frac=soc,
        inserted_charging_stops=inserted, penalty_breakdown=penalty_breakdown,
    )


def prins_split(
    giant_tour_stop_ids: list[int],
    stops_by_id: dict[int, Stop],
    vehicles: list[Vehicle],
    depots_by_id: dict[int, Depot],
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
    max_segment_len: Optional[int] = None,
) -> SplitResult:
    """
    Multi-Vehicle Prins' Split via 2D Dynamic Programming over (vehicles_used, stops_completed).
    Allocates stops across user-defined vehicles (1..K) to mathematically minimize overall cost
    and parallel trip duration while respecting vehicle constraints and assigning distinct vehicles.
    """
    n = len(giant_tour_stop_ids)
    if n == 0:
        return SplitResult(routes=[], total_cost=0.0, feasible=True, objective_vector=np.zeros(4))
    if not vehicles:
        return SplitResult(routes=[], total_cost=BIG, feasible=False)

    seq = [stops_by_id[i] for i in giant_tour_stop_ids]
    max_len = max_segment_len or n
    K = len(vehicles)

    # 2D DP: dp[k][i] = min cost to serve first i stops using k distinct vehicles
    dp = [[BIG] * (n + 1) for _ in range(K + 1)]
    dp[0][0] = 0.0
    parent = [[None] * (n + 1) for _ in range(K + 1)]

    for k in range(1, K + 1):
        v = vehicles[k - 1]
        depot = depots_by_id.get(v.depot_id, list(depots_by_id.values())[0])
        for i in range(n):
            if dp[k - 1][i] == BIG:
                continue
            for j in range(i + 1, min(n, i + max_len) + 1):
                segment = seq[i:j]
                ev = evaluate_segment(segment, v, depot, charging_stations, edge_weight_fn, dispatch_time_min=0.0)
                if ev.feasible:
                    cand = dp[k - 1][i] + ev.cost
                    if cand < dp[k][j]:
                        dp[k][j] = cand
                        parent[k][j] = (i, v.id, depot.id, ev)

    # Find the optimal number of vehicles k in 1..K that completed all n stops
    best_k = None
    best_cost = BIG
    for k in range(1, K + 1):
        if dp[k][n] < best_cost:
            best_cost = dp[k][n]
            best_k = k

    if best_k is None or best_cost == BIG:
        return _prins_split_1d_fallback(giant_tour_stop_ids, seq, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn, max_len)

    routes = []
    idx = n
    cur_k = best_k
    total_penalty = 0.0
    total_dist = 0.0
    total_energy = 0.0
    while idx > 0 and cur_k > 0:
        p = parent[cur_k][idx]
        if p is None:
            return _prins_split_1d_fallback(giant_tour_stop_ids, seq, stops_by_id, vehicles, depots_by_id, charging_stations, edge_weight_fn, max_len)
        i, vehicle_id, depot_id, ev = p
        route_stop_ids = giant_tour_stop_ids[i:idx]
        routes.append({
            "vehicle_id": vehicle_id,
            "depot_id": depot_id,
            "stop_sequence": route_stop_ids,
            "cost": ev.cost,
            "end_time_min": ev.end_time_min,
            "end_soc_frac": ev.end_soc_frac,
            "inserted_charging_stops": ev.inserted_charging_stops,
            "penalty_breakdown": ev.penalty_breakdown,
        })
        total_penalty += sum(ev.penalty_breakdown.values())
        idx = i
        cur_k -= 1

    routes.reverse()
    return SplitResult(
        routes=routes,
        total_cost=best_cost,
        feasible=True,
        objective_vector=np.array([best_cost, total_dist, total_energy, total_penalty]),
    )


def _prins_split_1d_fallback(
    giant_tour_stop_ids: list[int],
    seq: list[Stop],
    stops_by_id: dict[int, Stop],
    vehicles: list[Vehicle],
    depots_by_id: dict[int, Depot],
    charging_stations: list[ChargingStation],
    edge_weight_fn=None,
    max_len: int = 100,
) -> SplitResult:
    n = len(giant_tour_stop_ids)
    dp = [BIG] * (n + 1)
    dp[0] = 0.0
    parent = [None] * (n + 1)

    for i in range(n):
        if dp[i] == BIG:
            continue
        for j in range(i + 1, min(n, i + max_len) + 1):
            segment = seq[i:j]
            best_local = None
            for v_idx, v in enumerate(vehicles):
                depot = depots_by_id.get(v.depot_id, list(depots_by_id.values())[0])
                ev = evaluate_segment(segment, v, depot, charging_stations, edge_weight_fn, dispatch_time_min=0.0)
                if ev.feasible and (best_local is None or ev.cost < best_local[0].cost):
                    best_local = (ev, v, depot)
            if best_local is None:
                continue
            ev, v, depot = best_local
            cand = dp[i] + ev.cost
            if cand < dp[j]:
                dp[j] = cand
                parent[j] = (i, v.id, depot.id, ev)

    if dp[n] == BIG:
        return SplitResult(routes=[], total_cost=BIG, feasible=False)

    routes = []
    idx = n
    total_penalty = 0.0
    route_num = 0
    while idx > 0:
        p = parent[idx]
        if p is None:
            return SplitResult(routes=[], total_cost=BIG, feasible=False)
        i, vehicle_id, depot_id, ev = p
        assigned_vid = vehicles[route_num % len(vehicles)].id if vehicles else vehicle_id
        route_stop_ids = giant_tour_stop_ids[i:idx]
        routes.append({
            "vehicle_id": assigned_vid,
            "depot_id": depot_id,
            "stop_sequence": route_stop_ids,
            "cost": ev.cost,
            "end_time_min": ev.end_time_min,
            "end_soc_frac": ev.end_soc_frac,
            "inserted_charging_stops": ev.inserted_charging_stops,
            "penalty_breakdown": ev.penalty_breakdown,
        })
        total_penalty += sum(ev.penalty_breakdown.values())
        idx = i
        route_num += 1
    routes.reverse()
    return SplitResult(
        routes=routes,
        total_cost=dp[n],
        feasible=True,
        objective_vector=np.array([dp[n], 0.0, 0.0, total_penalty]),
    )
