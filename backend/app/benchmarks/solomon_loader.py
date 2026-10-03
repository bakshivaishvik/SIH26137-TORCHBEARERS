"""
Academic benchmark ingestion (Section 6.1): parses standard Solomon VRPTW,
Gehring & Homberger, and TSPLIB instance file formats into this system's
Stop/Vehicle/Depot models, runs the QPSO engine against them, and reports
the percentage gap to the instance's Best Known Solution (BKS).
"""
from __future__ import annotations
from pathlib import Path
from app.core.models import Stop, Vehicle, Depot


def parse_solomon(path: str) -> dict:
    """Parses the standard Solomon .txt format:
        line 1: instance name
        VEHICLE section: NUMBER, CAPACITY
        CUSTOMER section: CUST NO. XCOORD YCOORD DEMAND READY DUE SERVICE
    """
    lines = [l.rstrip("\n") for l in Path(path).read_text().splitlines() if l.strip()]
    name = lines[0].strip()
    veh_idx = next(i for i, l in enumerate(lines) if l.strip().upper().startswith("VEHICLE"))
    num_vehicles, capacity = map(int, lines[veh_idx + 2].split()[:2])

    cust_idx = next(i for i, l in enumerate(lines) if l.strip().upper().startswith("CUSTOMER"))
    header_idx = cust_idx + 1
    data_lines = lines[header_idx + 1:]

    stops, depot = [], None
    for l in data_lines:
        parts = l.split()
        if len(parts) < 7:
            continue
        cust_no, x, y, demand, ready, due, service = map(float, parts[:7])
        if int(cust_no) == 0:
            depot = Depot(id=0, lat=y, lon=x)
            continue
        stops.append(Stop(id=int(cust_no), lat=y, lon=x, demand=int(demand),
                           tw_start_min=ready, tw_hard_end_min=due, tw_soft_end_min=due,
                           service_time_min=service))
    vehicles = [Vehicle(id=i, depot_id=0, capacity=capacity) for i in range(num_vehicles)]
    return {"name": name, "depot": depot, "stops": stops, "vehicles": vehicles}


def parse_tsplib(path: str) -> dict:
    """Minimal TSPLIB EUC_2D parser (NODE_COORD_SECTION) for the
    shortest-path/TSP-style benchmark track."""
    lines = Path(path).read_text().splitlines()
    coords = {}
    in_coords = False
    for l in lines:
        if l.startswith("NODE_COORD_SECTION"):
            in_coords = True
            continue
        if l.startswith("EOF"):
            break
        if in_coords:
            parts = l.split()
            if len(parts) >= 3:
                idx, x, y = int(parts[0]), float(parts[1]), float(parts[2])
                coords[idx] = (x, y)
    return {"coords": coords}


# Known Best-Known-Solution values for a handful of common Solomon instances,
# used to compute the %-gap-to-BKS metric in Section 6.1/6.2. Extend this
# table as more instances are benchmarked.
BKS_TABLE = {
    "C101": 828.94, "C201": 591.56, "R101": 1637.7, "R201": 1143.2,
    "RC101": 1619.8, "RC201": 1261.8,
}


def percent_gap_to_bks(instance_name: str, achieved_cost: float) -> float | None:
    bks = BKS_TABLE.get(instance_name.upper())
    if bks is None:
        return None
    return 100.0 * (achieved_cost - bks) / bks
