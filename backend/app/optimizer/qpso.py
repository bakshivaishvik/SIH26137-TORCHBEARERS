"""
Quantum Particle Swarm Optimization (QPSO) core search.

Each particle is an N-dimensional real vector, one dimension per
customer/incident stop. Particles are updated using the delta-potential-well
model (Sun et al.) around pBest and the swarm Mean Best Position (mBest),
governed by a contraction-expansion coefficient alpha that is annealed
across iterations (adaptive quantum parameter tuning) to avoid premature
convergence.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class QPSOConfig:
    n_particles: int = 40
    n_dims: int = 10
    max_iter: int = 150
    alpha_start: float = 1.2          # exploration-heavy contraction-expansion coeff
    alpha_end: float = 0.35           # exploitation-heavy coeff late in run
    alpha_schedule: str = "nonlinear"  # "linear" | "nonlinear" | "diversity_feedback"
    bounds: tuple = (0.0, 1.0)
    seed: Optional[int] = None


class QPSOSwarm:
    """
    A quantum-behaved particle swarm operating over continuous [0,1]^N space.
    The decoding of a position vector into a routing solution (via SPV +
    Prins' Split) is left to the caller through `fitness_fn`, which must
    accept a (n_particles, n_dims) matrix of positions and return a
    (n_particles,) array of scalar fitness (lower is better) OR, for
    multi-objective mode, a (n_particles, n_objectives) matrix.
    """

    def __init__(self, config: QPSOConfig, fitness_fn: Callable[[np.ndarray], np.ndarray],
                 multi_objective: bool = False):
        self.cfg = config
        self.fitness_fn = fitness_fn
        self.multi_objective = multi_objective
        self.rng = np.random.default_rng(config.seed)

        lo, hi = config.bounds
        self.positions = self.rng.uniform(lo, hi, size=(config.n_particles, config.n_dims))
        self.pbest = self.positions.copy()

        init_fit = self._evaluate(self.positions)
        self.pbest_fit = init_fit.copy()

        if multi_objective:
            # scalarize with equal weights just to seed gbest; true multi-obj
            # ranking is handled by pareto.py after the run.
            scalar = init_fit.sum(axis=1)
            self.gbest = self.positions[np.argmin(scalar)].copy()
            self.gbest_fit = init_fit[np.argmin(scalar)].copy()
        else:
            self.gbest = self.positions[np.argmin(init_fit)].copy()
            self.gbest_fit = init_fit.min()

        self.convergence_history: list[float] = []
        self.diversity_history: list[float] = []
        self.all_positions_history: list[np.ndarray] = []  # for the particle visualizer

    def _evaluate(self, positions: np.ndarray) -> np.ndarray:
        return self.fitness_fn(positions)

    def _swarm_diversity(self) -> float:
        centroid = self.positions.mean(axis=0)
        return float(np.mean(np.linalg.norm(self.positions - centroid, axis=1)))

    def _alpha(self, t: int, diversity: float) -> float:
        cfg = self.cfg
        frac = t / max(cfg.max_iter - 1, 1)
        if cfg.alpha_schedule == "linear":
            return cfg.alpha_start + (cfg.alpha_end - cfg.alpha_start) * frac
        if cfg.alpha_schedule == "diversity_feedback":
            # low diversity -> bump alpha back up to re-inject exploration
            # (lets the swarm tunnel out of local optima instead of collapsing)
            base = cfg.alpha_start + (cfg.alpha_end - cfg.alpha_start) * frac
            boost = 0.5 * np.exp(-8.0 * diversity)  # diversity in [0, ~0.3] typically
            return float(np.clip(base + boost, cfg.alpha_end, cfg.alpha_start + 0.5))
        # nonlinear (cosine) decay - default
        return cfg.alpha_end + 0.5 * (cfg.alpha_start - cfg.alpha_end) * (1 + np.cos(np.pi * frac))

    def step(self, t: int) -> None:
        cfg = self.cfg
        n, d = cfg.n_particles, cfg.n_dims
        diversity = self._swarm_diversity()
        alpha = self._alpha(t, diversity)

        mbest = self.pbest.mean(axis=0)  # Mean Best Position across swarm

        phi = self.rng.uniform(0, 1, size=(n, d))
        p = phi * self.pbest + (1 - phi) * self.gbest  # local attractor point

        u = self.rng.uniform(1e-9, 1.0, size=(n, d))
        sign = np.where(self.rng.uniform(size=(n, d)) < 0.5, 1.0, -1.0)

        # delta-potential-well update: particle tunnels toward attractor p
        self.positions = p + sign * alpha * np.abs(mbest - self.positions) * np.log(1.0 / u)

        lo, hi = cfg.bounds
        self.positions = np.clip(self.positions, lo, hi)

        fit = self._evaluate(self.positions)

        if self.multi_objective:
            scalar_new = fit.sum(axis=1)
            scalar_old = self.pbest_fit.sum(axis=1)
            improved = scalar_new < scalar_old
        else:
            improved = fit < self.pbest_fit

        self.pbest[improved] = self.positions[improved]
        self.pbest_fit[improved] = fit[improved]

        if self.multi_objective:
            scalar = self.pbest_fit.sum(axis=1)
            best_idx = np.argmin(scalar)
            if scalar[best_idx] < self.gbest_fit.sum():
                self.gbest = self.pbest[best_idx].copy()
                self.gbest_fit = self.pbest_fit[best_idx].copy()
            self.convergence_history.append(float(self.gbest_fit.sum()))
        else:
            best_idx = np.argmin(self.pbest_fit)
            if self.pbest_fit[best_idx] < self.gbest_fit:
                self.gbest = self.pbest[best_idx].copy()
                self.gbest_fit = float(self.pbest_fit[best_idx])
            self.convergence_history.append(float(self.gbest_fit))

        self.diversity_history.append(diversity)
        self.all_positions_history.append(self.positions.copy())

    def run(self) -> None:
        for t in range(self.cfg.max_iter):
            self.step(t)

    def latest_snapshot(self) -> dict:
        """Real-time particle-state snapshot for the Particle Visualizer (Section 5.3)."""
        return {
            "positions": self.positions.tolist(),
            "pbest": self.pbest.tolist(),
            "gbest": self.gbest.tolist(),
            "diversity": self.diversity_history[-1] if self.diversity_history else None,
        }
