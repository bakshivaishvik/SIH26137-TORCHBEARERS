"""
Qubit Quantum Particle Swarm Optimization (Q-QPSO) core search.

Each particle maintains an N-dimensional Qubit state vector:
    |ψ_i,d⟩ = α_i,d |0⟩ + β_i,d |1⟩
where α_i,d = cos(θ_i,d) and β_i,d = sin(θ_i,d), guaranteeing the quantum
normalization condition |α|^2 + |β|^2 = 1.

Quantum states are updated via Quantum Rotation Gates R_y(Δθ):
    [ α(t+1) ]   [ cos(Δθ)  -sin(Δθ) ] [ α(t) ]
    [ β(t+1) ] = [ sin(Δθ)   cos(Δθ) ] [ β(t) ]

A Quantum Pauli-X (NOT) Mutation Gate is applied with low probability to
swap amplitudes |α|^2 <-> |β|^2, allowing particles to tunnel out of local optima.

The continuous position vector X_i in [0,1]^N is obtained via quantum measurement
collapse x_i,d = |β_i,d|^2 = sin^2(θ_i,d), which feeds directly into SPV decoding.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class QubitQPSOConfig:
    n_particles: int = 40
    n_dims: int = 10
    max_iter: int = 150
    w_start: float = 0.9           # inertia weight on rotation step
    w_end: float = 0.4
    c1: float = 1.5                # cognitive parameter toward pBest phase
    c2: float = 1.5                # social parameter toward gBest phase
    mutation_rate: float = 0.05    # Pauli-X quantum mutation gate probability
    bounds: tuple = (0.0, 1.0)
    seed: Optional[int] = None


class QubitQPSOSwarm:
    """
    A Qubit-encoded quantum particle swarm using R_y rotation gates.
    """

    def __init__(self, config: QubitQPSOConfig, fitness_fn: Callable[[np.ndarray], np.ndarray],
                 multi_objective: bool = False):
        self.cfg = config
        self.fitness_fn = fitness_fn
        self.multi_objective = multi_objective
        self.rng = np.random.default_rng(config.seed)

        n, d = config.n_particles, config.n_dims
        # Qubit phase angles θ in [0, 2π]
        self.theta = self.rng.uniform(0.0, 2.0 * np.pi, size=(n, d))
        # Quantum rotation velocity Δθ
        self.delta_theta = np.zeros((n, d))

        # Personal best phase angles
        self.pbest_theta = self.theta.copy()

        # Measurement collapse to continuous coordinates in [0,1]^N
        self.positions = np.sin(self.theta) ** 2
        self.pbest_positions = self.positions.copy()

        # Evaluate initial fitness
        init_fit = self._evaluate(self.positions)
        self.pbest_fit = init_fit.copy()

        if multi_objective:
            scalar = init_fit.sum(axis=1)
            best_idx = np.argmin(scalar)
            self.gbest_theta = self.theta[best_idx].copy()
            self.gbest_position = self.positions[best_idx].copy()
            self.gbest_fit = init_fit[best_idx].copy()
        else:
            best_idx = np.argmin(init_fit)
            self.gbest_theta = self.theta[best_idx].copy()
            self.gbest_position = self.positions[best_idx].copy()
            self.gbest_fit = float(init_fit.min())

        self.convergence_history: list[float] = []
        self.diversity_history: list[float] = []
        self.all_positions_history: list[np.ndarray] = []
        self.all_theta_history: list[np.ndarray] = []

    @property
    def alpha(self) -> np.ndarray:
        """Qubit probability amplitude α = cos(θ)."""
        return np.cos(self.theta)

    @property
    def beta(self) -> np.ndarray:
        """Qubit probability amplitude β = sin(θ)."""
        return np.sin(self.theta)

    def verify_normalization(self) -> bool:
        """Verify quantum state normalization: |α|^2 + |β|^2 = 1."""
        norm = self.alpha ** 2 + self.beta ** 2
        return bool(np.allclose(norm, 1.0))

    def _evaluate(self, positions: np.ndarray) -> np.ndarray:
        return self.fitness_fn(positions)

    def _swarm_diversity(self) -> float:
        centroid = self.positions.mean(axis=0)
        return float(np.mean(np.linalg.norm(self.positions - centroid, axis=1)))

    def step(self, t: int) -> None:
        cfg = self.cfg
        n, d = cfg.n_particles, cfg.n_dims
        frac = t / max(cfg.max_iter - 1, 1)
        w = cfg.w_start + (cfg.w_end - cfg.w_start) * frac

        r1 = self.rng.uniform(0.0, 1.0, size=(n, d))
        r2 = self.rng.uniform(0.0, 1.0, size=(n, d))

        # Quantum Rotation Angle step Δθ toward pBest and gBest phase angles
        self.delta_theta = (w * self.delta_theta +
                            cfg.c1 * r1 * (self.pbest_theta - self.theta) +
                            cfg.c2 * r2 * (self.gbest_theta - self.theta))

        # Apply Quantum Rotation Gate R_y(Δθ): θ(t+1) = θ(t) + Δθ(t)
        self.theta = (self.theta + self.delta_theta) % (2.0 * np.pi)

        # Apply Quantum Pauli-X (NOT) Mutation Gate with probability mutation_rate
        mut_mask = self.rng.uniform(0.0, 1.0, size=(n, d)) < cfg.mutation_rate
        # NOT mutation swaps |α|^2 <-> |β|^2, equivalent to θ -> π/2 - θ
        self.theta = np.where(mut_mask, (np.pi / 2.0 - self.theta) % (2.0 * np.pi), self.theta)

        # Quantum Measurement Collapse: continuous position x_i,d = |β_i,d|^2 = sin^2(θ_i,d)
        self.positions = np.sin(self.theta) ** 2

        # Evaluate fitness of decoded routes
        fit = self._evaluate(self.positions)

        if self.multi_objective:
            scalar_new = fit.sum(axis=1)
            scalar_old = self.pbest_fit.sum(axis=1)
            improved = scalar_new < scalar_old
        else:
            improved = fit < self.pbest_fit

        self.pbest_theta[improved] = self.theta[improved]
        self.pbest_positions[improved] = self.positions[improved]
        self.pbest_fit[improved] = fit[improved]

        if self.multi_objective:
            scalar = self.pbest_fit.sum(axis=1)
            best_idx = np.argmin(scalar)
            if scalar[best_idx] < self.gbest_fit.sum():
                self.gbest_theta = self.pbest_theta[best_idx].copy()
                self.gbest_position = self.pbest_positions[best_idx].copy()
                self.gbest_fit = self.pbest_fit[best_idx].copy()
            self.convergence_history.append(float(self.gbest_fit.sum()))
        else:
            best_idx = np.argmin(self.pbest_fit)
            if self.pbest_fit[best_idx] < self.gbest_fit:
                self.gbest_theta = self.pbest_theta[best_idx].copy()
                self.gbest_position = self.pbest_positions[best_idx].copy()
                self.gbest_fit = float(self.pbest_fit[best_idx])
            self.convergence_history.append(float(self.gbest_fit))

        div = self._swarm_diversity()
        self.diversity_history.append(div)
        self.all_positions_history.append(self.positions.copy())
        self.all_theta_history.append(self.theta.copy())

    def run(self) -> None:
        for t in range(self.cfg.max_iter):
            self.step(t)

    @property
    def gbest(self) -> np.ndarray:
        """Alias for gbest_position to match QPSOSwarm API."""
        return self.gbest_position

    @property
    def pbest(self) -> np.ndarray:
        """Alias for pbest_positions to match QPSOSwarm API."""
        return self.pbest_positions

    def latest_snapshot(self) -> dict:
        """Real-time particle and qubit state snapshot for the Visualizer."""
        return {
            "positions": self.positions.tolist(),
            "theta": self.theta.tolist(),
            "alpha": self.alpha.tolist(),
            "beta": self.beta.tolist(),
            "pbest": self.pbest_positions.tolist(),
            "gbest": self.gbest_position.tolist(),
            "diversity": self.diversity_history[-1] if self.diversity_history else None,
        }
