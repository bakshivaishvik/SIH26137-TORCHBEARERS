#!/usr/bin/env python3
"""
Full-loop smoke test (Deliverable 2): place a hazard -> see the reroute ->
see the explainability log entry, exercised end-to-end against a running
backend (docker-compose up, or `uvicorn app.main:app` directly).

Usage:
    python smoke_test.py [--base-url http://localhost:8000]

Exits non-zero (with a printed reason) on any failed step, so it's usable
as a CI gate as well as a jury-demo dry run.
"""
from __future__ import annotations
import sys
import time
import argparse
import httpx


def step(name):
    def deco(fn):
        def wrapper(*a, **kw):
            print(f"\n== {name} ==")
            result = fn(*a, **kw)
            print(f"   OK")
            return result
        return wrapper
    return deco


@step("1. Health check")
def check_health(client):
    r = client.get("/health")
    r.raise_for_status()
    assert r.json()["status"] == "ok"


@step("2. Reset a fresh demo scenario")
def reset_scenario(client):
    r = client.post("/api/scenario/reset", json={"n_stops": 12, "n_vehicles": 4, "seed": 7})
    r.raise_for_status()


@step("3. Run full QPSO optimize() over the scenario")
def run_optimize(client):
    r = client.post("/api/optimize", json={"n_particles": 30, "max_iter": 60, "seed": 1})
    r.raise_for_status()
    data = r.json()
    assert data["feasible"], "optimizer returned infeasible on the demo scenario"
    assert len(data["routes"]) > 0
    print(f"   {len(data['routes'])} route(s), total_cost={data['total_cost']:.2f}")
    return data


@step("4. Place a hazard on the map (Chaos Mode)")
def place_hazard(client, scenario_snapshot):
    # aim near the first route's first stop so the hazard has a good chance
    # of actually touching an active route
    stops = scenario_snapshot.get("stops") or []
    target = stops[0] if stops else {"lat": 12.9716, "lon": 77.5946}
    r = client.post("/api/chaos/hazard", json={"lat": target["lat"], "lon": target["lon"], "hazard_type": "roadblock"})
    r.raise_for_status()
    data = r.json()
    print(f"   reoptimized_route_ids={data['reoptimized_route_ids']}  wall_clock_sec={data['wall_clock_sec']:.4f}")
    assert data["wall_clock_sec"] < 5.0, "delta re-optimization took too long for a city-block-sized disruption"
    return data


@step("5. Confirm the hazard produced an explainability log entry")
def check_explainability(client):
    r = client.get("/api/explainability", params={"event_type": "hazard", "limit": 1})
    r.raise_for_status()
    entries = r.json()
    assert len(entries) > 0, "no hazard decision was logged"
    print(f"   narrative: {entries[0]['narrative']}")


@step("6. Dynamic on-the-fly incident insertion")
def insert_incident(client):
    r = client.post("/api/insert", json={"lat": 12.98, "lon": 77.61, "triage": "CRITICAL", "sla_response_min": 20})
    r.raise_for_status()
    data = r.json()
    assert data["success"], f"insertion failed: {data}"
    print(f"   strategy={data['strategy']} vehicle_id={data.get('vehicle_id')} marginal_cost={data.get('marginal_cost')}")


@step("7. 5-way Algorithm Arena run")
def run_arena(client):
    r = client.post("/api/arena/run", json={"n_agents": 15, "max_iter": 30, "seed": 2})
    r.raise_for_status()
    data = r.json()
    for name in ("dijkstra", "astar", "genetic_algorithm", "standard_pso", "gwo", "qpso", "qubit_qpso"):
        assert name in data, f"arena missing algorithm: {name}"
    print("   all 6 algorithms returned a result")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=60.0)

    t0 = time.time()
    check_health(client)
    reset_scenario(client)
    optimize_result = run_optimize(client)
    scenario_snapshot = client.get("/api/scenario").json()
    place_hazard(client, scenario_snapshot)
    check_explainability(client)
    insert_incident(client)
    run_arena(client)

    print(f"\n✅ Full loop smoke test passed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n❌ SMOKE TEST FAILED: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"\n❌ SMOKE TEST FAILED: HTTP {e.response.status_code} on {e.request.url}\n{e.response.text[:500]}")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"\n❌ SMOKE TEST FAILED: could not connect to backend. Is it running? "
              f"(docker compose up, or uvicorn app.main:app --port 8000)")
        sys.exit(1)
