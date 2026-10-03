"""
Realistic synthetic traffic time-series generator, used to feed the ST-GNN
trainer (Section 2.1) and to stand in for SUMO's TraCI output stream
(Section 3) when a live SUMO binary/network isn't running in this
environment. Produces a daily double-peak (morning/evening rush) profile
per edge with spatial correlation (nearby edges are correlated) and
gaussian sensor noise -- structurally realistic, not pure random noise.
"""
from __future__ import annotations
import numpy as np


def generate_traffic_tensor(n_edges: int, n_timesteps: int, dt_min: int = 5, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(n_timesteps) * dt_min / 60.0  # hours
    morning = np.exp(-((t - 8.5) ** 2) / (2 * 1.1 ** 2))
    evening = np.exp(-((t - 18.0) ** 2) / (2 * 1.3 ** 2))
    base_profile = 0.25 + 0.9 * morning + 0.75 * evening  # congestion index base curve

    edge_phase_shift = rng.normal(0, 0.35, size=n_edges)
    edge_amplitude = rng.uniform(0.7, 1.3, size=n_edges)

    tensor = np.zeros((n_edges, n_timesteps))
    for e in range(n_edges):
        shifted_t = t + edge_phase_shift[e]
        m = np.exp(-((shifted_t - 8.5) ** 2) / (2 * 1.1 ** 2))
        ev = np.exp(-((shifted_t - 18.0) ** 2) / (2 * 1.3 ** 2))
        profile = (0.25 + 0.9 * m + 0.75 * ev) * edge_amplitude[e]
        noise = rng.normal(0, 0.05, size=n_timesteps)
        tensor[e] = np.clip(profile + noise, 0.05, 3.0)
    return tensor  # congestion multiplier per edge per timestep, shape (n_edges, n_timesteps)


def build_supervised_windows(tensor: np.ndarray, lookback: int, horizons: list[int]):
    """Slice the (n_edges, T) tensor into (X, y) supervised windows for
    training: X = last `lookback` steps, y = value at each horizon ahead."""
    n_edges, T = tensor.shape
    max_h = max(horizons)
    X, Y = [], []
    for start in range(0, T - lookback - max_h):
        X.append(tensor[:, start:start + lookback])
        Y.append(np.stack([tensor[:, start + lookback + h - 1] for h in horizons], axis=-1))
    return np.array(X), np.array(Y)  # X: (N, n_edges, lookback), Y: (N, n_edges, n_horizons)
