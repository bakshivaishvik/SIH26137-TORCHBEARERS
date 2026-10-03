"""Unit tests for the mathematical core (Section 1) -- run with `pytest`."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
from app.core.models import Stop, Vehicle, Depot, Triage
from app.optimizer.spv import spv_decode, spv_decode_batch
from app.optimizer.split import prins_split
from app.optimizer.engine import optimize, OptimizeConstraints
from app.optimizer.pareto import fast_non_dominated_sort, pareto_front
from app.optimizer.delta_reopt import localized_delta_reopt


def test_spv_decode_matches_spec_example():
    vec = np.array([0.82, 0.15, 0.67, 0.44, 0.91])
    perm = spv_decode(vec)
    assert list(perm) == [1, 3, 2, 0, 4]  # 0-indexed version of 2->4->3->1->5


def test_spv_decode_batch_shape():
    positions = np.random.default_rng(0).uniform(size=(10, 6))
    perms = spv_decode_batch(positions)
    assert perms.shape == (10, 6)
    for row in perms:
        assert sorted(row) == list(range(6))


def test_prins_split_feasible_simple_case():
    depot = Depot(id=0, lat=0.0, lon=0.0)
    stops = {i: Stop(id=i, lat=0.001 * i, lon=0.0, tw_hard_end_min=1000) for i in range(1, 4)}
    vehicles = [Vehicle(id=0, depot_id=0, capacity=5)]
    result = prins_split([1, 2, 3], stops, vehicles, {0: depot}, [])
    assert result.feasible
    assert len(result.routes) == 1
    assert result.routes[0]["stop_sequence"] == [1, 2, 3]


def test_prins_split_respects_hard_time_window():
    depot = Depot(id=0, lat=0.0, lon=0.0)
    far_stop = Stop(id=1, lat=5.0, lon=5.0, tw_hard_end_min=0.001)  # impossible to reach in time
    vehicles = [Vehicle(id=0, depot_id=0, capacity=5)]
    result = prins_split([1], {1: far_stop}, vehicles, {0: depot}, [])
    assert not result.feasible


def test_optimize_end_to_end_feasible():
    depot = Depot(id=0, lat=12.97, lon=77.59)
    rng = np.random.default_rng(3)
    stops = [Stop(id=i + 1, lat=12.97 + rng.uniform(-0.02, 0.02), lon=77.59 + rng.uniform(-0.02, 0.02),
                   tw_hard_end_min=500, tw_soft_end_min=150) for i in range(6)]
    vehicles = [Vehicle(id=i, depot_id=0, capacity=4) for i in range(2)]

    class G:
        edge_weight_fn = None

    result = optimize(G(), stops, vehicles, [depot], [], OptimizeConstraints(n_particles=15, max_iter=20, seed=1))
    assert result["feasible"]
    assert result["total_cost"] is not None
    assert len(result["convergence_history"]) == 20


def test_pareto_sort_basic_dominance():
    objs = np.array([[1.0, 5.0], [2.0, 2.0], [5.0, 1.0], [3.0, 3.0]])
    fronts = fast_non_dominated_sort(objs)
    assert 3 in fronts[-1] or len(fronts) >= 1  # (3,3) is dominated by (2,2); sanity check it's not in front 0
    front0 = fronts[0]
    assert 3 not in front0


from app.optimizer.qqpso import QubitQPSOSwarm, QubitQPSOConfig


def test_qubit_qpso_normalization_and_step():
    cfg = QubitQPSOConfig(n_particles=10, n_dims=5, max_iter=5, seed=42)
    def dummy_fit(pos):
        return pos.sum(axis=1)

    swarm = QubitQPSOSwarm(cfg, dummy_fit)
    # Check normalization condition: |α|^2 + |β|^2 = 1
    assert swarm.verify_normalization()
    
    # Step through iterations and verify normalization is preserved
    for t in range(5):
        swarm.step(t)
        assert swarm.verify_normalization()
        assert swarm.positions.min() >= 0.0 and swarm.positions.max() <= 1.0

    assert len(swarm.convergence_history) == 5
    snapshot = swarm.latest_snapshot()
    assert "theta" in snapshot and "alpha" in snapshot and "beta" in snapshot


def test_optimize_qubit_qpso_end_to_end():
    depot = Depot(id=0, lat=12.97, lon=77.59)
    rng = np.random.default_rng(7)
    stops = [Stop(id=i + 1, lat=12.97 + rng.uniform(-0.02, 0.02), lon=77.59 + rng.uniform(-0.02, 0.02),
                   tw_hard_end_min=500, tw_soft_end_min=150) for i in range(6)]
    vehicles = [Vehicle(id=i, depot_id=0, capacity=4) for i in range(2)]

    class G:
        edge_weight_fn = None

    result = optimize(G(), stops, vehicles, [depot], [],
                      OptimizeConstraints(n_particles=15, max_iter=20, algorithm_type="qubit_qpso", seed=1))
    assert result["feasible"]
    assert result["total_cost"] is not None
    assert len(result["convergence_history"]) == 20

