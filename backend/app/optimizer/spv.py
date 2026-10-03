"""
SPV (Smallest Position Value) decoding.

Converts a continuous QPSO particle vector into a discrete permutation
("giant tour") by sorting the real values ascending and reading off the
original indices.

Example: [0.82, 0.15, 0.67, 0.44, 0.91] -> sorted [0.15,0.44,0.67,0.82,0.91]
         -> giant tour 2 -> 4 -> 3 -> 1 -> 5  (1-indexed stop IDs)
"""
from __future__ import annotations
import numpy as np


def spv_decode(position: np.ndarray) -> np.ndarray:
    """Decode a single particle's continuous vector into a permutation of
    0-indexed stop indices, via argsort (ties broken by original order)."""
    return np.argsort(position, kind="stable")


def spv_decode_batch(positions: np.ndarray) -> np.ndarray:
    """Vectorized SPV decode for a whole swarm: (n_particles, n_dims) ->
    (n_particles, n_dims) integer permutation matrix."""
    return np.argsort(positions, axis=1, kind="stable")
