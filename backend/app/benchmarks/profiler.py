"""
Statistical performance profiler (Section 6.2) + memory/computational
footprint dashboard backing (Section 6.3).

Produces: convergence curves, scalability benchmarks (N=20->1000 vs
latency ms), solution-consistency across multi-seed Monte Carlo runs, and
live memory/thread/CPU utilization samples during a swarm run.
"""
from __future__ import annotations
import time
import threading
import numpy as np
import psutil

from app.core.models import Stop, Vehicle, Depot
from app.optimizer.engine import optimize, OptimizeConstraints


class ResourceMonitor:
    """Live-tracks memory usage, thread count and CPU utilization on a
    background sampling thread while an optimization run is in progress
    (Section 6.3), independent of any UI framework."""

    def __init__(self, interval_sec: float = 0.25):
        self.interval_sec = interval_sec
        self.samples: list[dict] = []
        self._stop_flag = threading.Event()
        self._thread = None
        self._proc = psutil.Process()

    def _run(self):
        while not self._stop_flag.is_set():
            self.samples.append({
                "ts": time.time(),
                "rss_mb": self._proc.memory_info().rss / (1024 * 1024),
                "cpu_percent": self._proc.cpu_percent(interval=None),
                "n_threads": self._proc.num_threads(),
            })
            time.sleep(self.interval_sec)

    def start(self):
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict]:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2)
        return self.samples


def make_random_instance(n_stops: int, n_vehicles: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    depot = Depot(id=0, lat=12.9716, lon=77.5946)
    stops = [Stop(id=i + 1, lat=12.9716 + rng.uniform(-0.08, 0.08), lon=77.5946 + rng.uniform(-0.08, 0.08),
                   tw_start_min=0, tw_hard_end_min=600, tw_soft_end_min=200) for i in range(n_stops)]
    vehicles = [Vehicle(id=i, depot_id=0, capacity=max(2, n_stops // n_vehicles + 1)) for i in range(n_vehicles)]
    return {"depot": depot, "stops": stops, "vehicles": vehicles}


class _DummyGraph:
    edge_weight_fn = None


def scalability_benchmark(node_counts=(20, 50, 100, 250, 500, 1000), n_vehicles_fn=lambda n: max(2, n // 15),
                           max_iter: int = 60, n_particles: int = 30, seed: int = 0) -> list[dict]:
    """Node count N=20->1000 vs compute latency in ms (Section 6.2)."""
    out = []
    for n in node_counts:
        inst = make_random_instance(n, n_vehicles_fn(n), seed)
        t0 = time.perf_counter()
        result = optimize(_DummyGraph(), inst["stops"], inst["vehicles"], [inst["depot"]], [],
                           OptimizeConstraints(n_particles=n_particles, max_iter=max_iter, seed=seed))
        latency_ms = (time.perf_counter() - t0) * 1000
        out.append({"n_stops": n, "latency_ms": latency_ms, "feasible": result["feasible"],
                     "total_cost": result["total_cost"]})
    return out


def monte_carlo_consistency(n_stops: int, n_vehicles: int, n_seeds: int = 10,
                             max_iter: int = 80, n_particles: int = 30) -> dict:
    """Solution-consistency metric: standard deviation of final cost across
    multi-seed Monte Carlo runs on the SAME instance (Section 6.2)."""
    inst = make_random_instance(n_stops, n_vehicles, seed=999)
    costs = []
    for seed in range(n_seeds):
        result = optimize(_DummyGraph(), inst["stops"], inst["vehicles"], [inst["depot"]], [],
                           OptimizeConstraints(n_particles=n_particles, max_iter=max_iter, seed=seed))
        if result["feasible"]:
            costs.append(result["total_cost"])
    costs = np.array(costs)
    return {"n_runs": len(costs), "mean_cost": float(costs.mean()) if len(costs) else None,
             "std_cost": float(costs.std()) if len(costs) else None, "costs": costs.tolist()}
