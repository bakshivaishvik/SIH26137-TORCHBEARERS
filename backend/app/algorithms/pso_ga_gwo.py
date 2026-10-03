"""
Classical comparison algorithms for the 4/5-Way Algorithm Arena (Section 5.2):
standard Genetic Algorithm, standard (non-quantum) PSO, and Grey Wolf
Optimizer (GWO). All three search over the SAME representation as QPSO
(a continuous vector -> SPV decode -> Prins' Split fitness) so the
comparison against QPSO in engine.py/QPSOSwarm is apples-to-apples: same
decode, same feasibility/cost function, only the search operator differs.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Callable


@dataclass
class ClassicalConfig:
    n_agents: int = 40
    n_dims: int = 10
    max_iter: int = 150
    bounds: tuple = (0.0, 1.0)
    seed: int | None = None


class StandardPSO:
    """Textbook inertia-weight PSO (Kennedy & Eberhart), for benchmarking
    against QPSO's quantum delta-well update."""

    def __init__(self, cfg: ClassicalConfig, fitness_fn: Callable[[np.ndarray], np.ndarray]):
        self.cfg = cfg
        self.fitness_fn = fitness_fn
        self.rng = np.random.default_rng(cfg.seed)
        lo, hi = cfg.bounds
        self.pos = self.rng.uniform(lo, hi, (cfg.n_agents, cfg.n_dims))
        self.vel = self.rng.uniform(-0.1, 0.1, (cfg.n_agents, cfg.n_dims))
        self.pbest = self.pos.copy()
        self.pbest_fit = fitness_fn(self.pos)
        best = np.argmin(self.pbest_fit)
        self.gbest = self.pbest[best].copy()
        self.gbest_fit = float(self.pbest_fit[best])
        self.convergence_history = []
        self.w, self.c1, self.c2 = 0.72, 1.49, 1.49

    def run(self):
        lo, hi = self.cfg.bounds
        for _ in range(self.cfg.max_iter):
            r1 = self.rng.uniform(size=self.pos.shape)
            r2 = self.rng.uniform(size=self.pos.shape)
            self.vel = (self.w * self.vel + self.c1 * r1 * (self.pbest - self.pos)
                        + self.c2 * r2 * (self.gbest - self.pos))
            self.pos = np.clip(self.pos + self.vel, lo, hi)
            fit = self.fitness_fn(self.pos)
            improved = fit < self.pbest_fit
            self.pbest[improved] = self.pos[improved]
            self.pbest_fit[improved] = fit[improved]
            best = np.argmin(self.pbest_fit)
            if self.pbest_fit[best] < self.gbest_fit:
                self.gbest = self.pbest[best].copy()
                self.gbest_fit = float(self.pbest_fit[best])
            self.convergence_history.append(self.gbest_fit)
        return self


class GeneticAlgorithm:
    """Standard real-coded GA: tournament selection, blend crossover,
    gaussian mutation, elitism. Operates on the same continuous
    representation so SPV decode applies identically."""

    def __init__(self, cfg: ClassicalConfig, fitness_fn: Callable[[np.ndarray], np.ndarray],
                 mutation_rate: float = 0.1, elite_frac: float = 0.1):
        self.cfg = cfg
        self.fitness_fn = fitness_fn
        self.rng = np.random.default_rng(cfg.seed)
        lo, hi = cfg.bounds
        self.pop = self.rng.uniform(lo, hi, (cfg.n_agents, cfg.n_dims))
        self.mutation_rate = mutation_rate
        self.elite_n = max(1, int(elite_frac * cfg.n_agents))
        self.convergence_history = []
        self.gbest = None
        self.gbest_fit = float("inf")

    def _tournament(self, fit, k=3):
        idx = self.rng.integers(0, len(fit), size=k)
        return idx[np.argmin(fit[idx])]

    def run(self):
        lo, hi = self.cfg.bounds
        for _ in range(self.cfg.max_iter):
            fit = self.fitness_fn(self.pop)
            order = np.argsort(fit)
            if fit[order[0]] < self.gbest_fit:
                self.gbest_fit = float(fit[order[0]])
                self.gbest = self.pop[order[0]].copy()
            self.convergence_history.append(self.gbest_fit)

            new_pop = [self.pop[i].copy() for i in order[: self.elite_n]]
            while len(new_pop) < self.cfg.n_agents:
                pa = self.pop[self._tournament(fit)]
                pb = self.pop[self._tournament(fit)]
                alpha = self.rng.uniform(-0.25, 1.25, size=pa.shape)
                child = alpha * pa + (1 - alpha) * pb
                mask = self.rng.uniform(size=child.shape) < self.mutation_rate
                child = np.where(mask, child + self.rng.normal(0, 0.1, child.shape), child)
                new_pop.append(np.clip(child, lo, hi))
            self.pop = np.array(new_pop[: self.cfg.n_agents])
        return self


class GreyWolfOptimizer:
    """Standard GWO (Mirjalili et al. 2014): alpha/beta/delta leader wolves
    guide the pack, with the encircling coefficient `a` linearly decayed
    from 2 to 0 across iterations."""

    def __init__(self, cfg: ClassicalConfig, fitness_fn: Callable[[np.ndarray], np.ndarray]):
        self.cfg = cfg
        self.fitness_fn = fitness_fn
        self.rng = np.random.default_rng(cfg.seed)
        lo, hi = cfg.bounds
        self.pos = self.rng.uniform(lo, hi, (cfg.n_agents, cfg.n_dims))
        self.convergence_history = []
        self.gbest = None
        self.gbest_fit = float("inf")

    def run(self):
        lo, hi = self.cfg.bounds
        for t in range(self.cfg.max_iter):
            fit = self.fitness_fn(self.pos)
            order = np.argsort(fit)
            alpha, beta, delta = self.pos[order[0]], self.pos[order[1 % len(order)]], self.pos[order[2 % len(order)]]
            if fit[order[0]] < self.gbest_fit:
                self.gbest_fit = float(fit[order[0]])
                self.gbest = alpha.copy()
            self.convergence_history.append(self.gbest_fit)

            a = 2.0 - 2.0 * t / max(self.cfg.max_iter - 1, 1)
            new_pos = np.empty_like(self.pos)
            for leader in (alpha, beta, delta):
                pass
            r1 = self.rng.uniform(size=self.pos.shape)
            r2 = self.rng.uniform(size=self.pos.shape)
            A1, C1 = 2 * a * r1 - a, 2 * r2
            D_alpha = np.abs(C1 * alpha - self.pos)
            X1 = alpha - A1 * D_alpha

            r1 = self.rng.uniform(size=self.pos.shape); r2 = self.rng.uniform(size=self.pos.shape)
            A2, C2 = 2 * a * r1 - a, 2 * r2
            D_beta = np.abs(C2 * beta - self.pos)
            X2 = beta - A2 * D_beta

            r1 = self.rng.uniform(size=self.pos.shape); r2 = self.rng.uniform(size=self.pos.shape)
            A3, C3 = 2 * a * r1 - a, 2 * r2
            D_delta = np.abs(C3 * delta - self.pos)
            X3 = delta - A3 * D_delta

            self.pos = np.clip((X1 + X2 + X3) / 3.0, lo, hi)
        return self
