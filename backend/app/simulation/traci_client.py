"""
TraCI live-control client (Section 3): connects to a running SUMO instance
to pull real-time per-edge speed/flow data during a simulation, and feeds
it into the dynamic edge-weighting layer (app.graph.edge_weights) and the
ST-GNN's streaming input (app.forecasting).

Offline mode: when the `sumo`/`libsumo`/`traci` binaries are not installed
in the current environment (true for this sandbox), `--offline` replays a
structurally-realistic synthetic flow (same generator as
app.forecasting.synthetic_traffic) through the identical interface, so
`get_live_edge_speeds()` always returns data in the same shape whether the
real SUMO binary is present or not -- swapping to a real SUMO server is a
constructor-flag change.
"""
from __future__ import annotations
import time
from typing import Iterator

from app.forecasting.synthetic_traffic import generate_traffic_tensor


class TraCIBridge:
    def __init__(self, sumocfg_path: str | None = None, edge_ids: list[str] | None = None, offline: bool = True):
        self.offline = offline
        self.edge_ids = edge_ids or []
        self._offline_tensor = None
        self._t = 0
        if not offline:
            import traci  # real TraCI, requires SUMO_HOME + sumo binary installed
            self._traci = traci
            traci.start(["sumo", "-c", sumocfg_path])

    def _ensure_offline_tensor(self):
        if self._offline_tensor is None:
            self._offline_tensor = generate_traffic_tensor(n_edges=max(len(self.edge_ids), 1), n_timesteps=2000)

    def step(self) -> dict:
        if self.offline:
            self._ensure_offline_tensor()
            self._t = (self._t + 1) % self._offline_tensor.shape[1]
            return {eid: float(self._offline_tensor[i, self._t]) for i, eid in enumerate(self.edge_ids)}
        self._traci.simulationStep()
        return {eid: self._traci.edge.getLastStepMeanSpeed(eid) for eid in self.edge_ids}

    def stream(self, n_steps: int = 100, dt_sec: float = 1.0) -> Iterator[dict]:
        for _ in range(n_steps):
            yield self.step()
            if self.offline:
                time.sleep(0)  # no artificial delay needed for offline replay
            else:
                time.sleep(dt_sec)

    def close(self):
        if not self.offline:
            self._traci.close()
