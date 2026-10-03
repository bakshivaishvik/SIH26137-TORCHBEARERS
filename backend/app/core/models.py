"""
Shared domain models for the routing engine: incidents/stops, vehicles,
depots, charging stations and the road graph abstraction. Used by every
layer (optimizer, algorithms, graph, simulation) so there is exactly one
definition of "what a stop/vehicle/depot is" in the whole system.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional
import math


class Triage(IntEnum):
    """Lower number = higher priority (like ESI/START triage)."""
    CRITICAL = 1
    URGENT = 2
    STANDARD = 3
    NON_URGENT = 4


@dataclass
class Stop:
    id: int
    lat: float
    lon: float
    demand: int = 1                       # patients / units required
    service_time_min: float = 5.0
    tw_start_min: float = 0.0             # hard window opens
    tw_hard_end_min: float = 1440.0       # hard window closes (infeasible after)
    tw_soft_end_min: Optional[float] = None  # soft target; lateness beyond this is penalized
    sla_response_min: Optional[float] = None  # ambulance SLA: dispatch->arrival ceiling
    triage: Triage = Triage.STANDARD
    is_pickup: bool = False               # dynamic mid-route pickup (equipment/2nd patient)
    depot_group: Optional[int] = None     # restrict to a depot/sub-fleet if set
    elevation_m: float = 0.0
    requires_multi_capacity_vehicle: bool = False

    # Food delivery / simulation extensions
    order_id: Optional[str] = None
    stop_type: Optional[str] = None       # "PICKUP" or "DROPOFF"
    status: str = "PENDING"               # "PENDING", "COLLECTED", "DELIVERED"
    assigned_vehicle_id: Optional[int] = None

    def soft_end(self) -> float:
        return self.tw_soft_end_min if self.tw_soft_end_min is not None else self.tw_hard_end_min


@dataclass
class ChargingStation:
    id: int
    lat: float
    lon: float
    charge_rate_soc_per_min: float = 0.02   # fraction of battery per minute


@dataclass
class Depot:
    id: int
    lat: float
    lon: float


@dataclass
class Vehicle:
    id: int
    depot_id: int
    capacity: int = 4                     # multi-capacity support vehicle default
    is_single_patient: bool = False       # ambulance transport unit: capacity forced to 1
    battery_capacity_kwh: float = 60.0
    energy_kwh_per_km_flat: float = 0.18
    max_speed_kmh: float = 60.0
    crew_overtime_start_min: float = 480.0  # shift length before overtime penalty kicks in

    partner_start_lat: Optional[float] = None
    partner_start_lon: Optional[float] = None

    def __post_init__(self):
        if self.is_single_patient:
            self.capacity = 1


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def energy_for_leg_kwh(vehicle: Vehicle, dist_km: float, elevation_delta_m: float) -> float:
    """Non-linear-ish discharge model: base consumption scaled by a grade
    penalty (climbing costs extra, descending recovers some via regen,
    floored so descent can't 'generate' more than a modest discount)."""
    base = vehicle.energy_kwh_per_km_flat * dist_km
    if dist_km <= 1e-9:
        grade_pct = 0.0
    else:
        grade_pct = (elevation_delta_m / (dist_km * 1000.0)) * 100.0
    if grade_pct >= 0:
        factor = 1.0 + 0.045 * grade_pct        # climbing: nonlinear extra draw
    else:
        factor = max(0.6, 1.0 + 0.02 * grade_pct)  # descending: capped regen benefit
    return max(base * factor, 0.0)
