# Architecture & Section-to-File Mapping

Four-layer data flow (as specified in the build prompt):

```
1. Mathematical Core        -> backend/app/optimizer/*, backend/app/core/models.py
2. Spatial & Predictive     -> backend/app/graph/*, backend/app/forecasting/*, backend/app/simulation/*
3. Telemetry & Edge Integr. -> backend/app/integrations/mqtt_client.py, erp_webhook.py
4. Interface & Enterprise   -> frontend/*, backend/app/main.py, integrations/beckn_*, groq_copilot.py
```

A hazard placed in the Chaos Mode UI (frontend/src/components/ChaosMap.jsx)
POSTs to `backend/app/main.py::place_hazard`, which updates
`app/graph/edge_weights.py`'s live state, calls
`app/optimizer/delta_reopt.py::localized_delta_reopt`, writes a row via
`app/explainability/logger.py`, and broadcasts the new routes over
`/ws/live` to every connected client — the full loop the smoke test proves.

## Section-by-section map

### 1. Core Mathematical & Optimization Engine
| Spec section | File |
|---|---|
| 1.1 QPSO continuous search + adaptive α | `backend/app/optimizer/qpso.py` |
| 1.2 SPV decoding | `backend/app/optimizer/spv.py` |
| 1.3 Prins' Split (VRPTW, E-VRP, multi-depot/pickup, ambulance constraints) | `backend/app/optimizer/split.py` |
| 1.4 Deterministic constraint repair | `backend/app/optimizer/repair.py` |
| 1.5 Localized delta re-optimization | `backend/app/optimizer/delta_reopt.py` |
| 1.6 Multi-objective Pareto (NSGA-II) | `backend/app/optimizer/pareto.py` |
| 1.7 Fitness/learning loop | `backend/app/optimizer/engine.py` (fitness_fn closures) |
| 1.8 `optimize()` module boundary | `backend/app/optimizer/engine.py` |
| 4.2 Dynamic on-the-fly insertion | `backend/app/optimizer/insertion.py` |

### 2. Predictive AI & Graph Intelligence
| Spec section | File |
|---|---|
| 2.1 ST-GNN forecaster | `backend/app/forecasting/stgnn.py`, `train_stgnn.py`, `synthetic_traffic.py` |
| 2.2 Dynamic multi-factor edge weighting | `backend/app/graph/edge_weights.py` |
| 2.3 Turn-penalty / OSM graph / vehicle clearance | `backend/app/graph/osm_graph.py` |
| 2.4 Graph partitioning (Louvain) | `backend/app/graph/partition.py` |

### 3. Simulation Layer (SUMO)
| Spec section | File |
|---|---|
| SUMO network export + TraCI live control | `backend/app/simulation/sumo_network.py`, `traci_client.py` |

### 4. Next-Gen Operational Features
| Spec section | File |
|---|---|
| 4.1 GenAI Dispatcher Copilot (Groq function calling) | `backend/app/integrations/groq_copilot.py` |
| 4.2 Dynamic on-the-fly order insertion | `backend/app/optimizer/insertion.py`, exposed at `POST /api/insert` |

### 5. Live Jury Demo & Chaos Mode
| Spec section | File |
|---|---|
| 5.1 Interactive Chaos Mode map | `frontend/src/components/ChaosMap.jsx`, backend `POST /api/chaos/hazard` |
| 5.2 5-Way Algorithm Arena | `backend/app/algorithms/arena.py`, `pso_ga_gwo.py`, `dijkstra_astar.py`, `frontend/src/components/AlgorithmArena.jsx` |
| 5.3 Particle State Visualizer | `frontend/src/components/ParticleVisualizer.jsx` (fed by `qpso.py`'s `all_positions_history`) |

### 6. Benchmarking, Validation & Proof Suite
| Spec section | File |
|---|---|
| 6.1 Solomon/Gehring-Homberger/TSPLIB ingestion + %-gap-to-BKS | `backend/app/benchmarks/solomon_loader.py` |
| 6.2 Convergence/scalability/Monte-Carlo profiler | `backend/app/benchmarks/profiler.py`, `frontend/src/components/ProfilerDashboard.jsx` |
| 6.3 Live memory/CPU/thread dashboard | `backend/app/benchmarks/profiler.py::ResourceMonitor` |

### 7. Real-World Systems & Ecosystem Integrations
| Spec section | File |
|---|---|
| ONDC/Beckn LSP client + local mock registry | `backend/app/integrations/beckn_client.py`, `beckn_mock_server.py` |
| Self-hosted OSRM/GraphHopper client | `backend/app/graph/osrm_client.py` |
| Client mapping/navigation | `frontend/src/components/ChaosMap.jsx` |
| ERP/WMS webhooks (SAP/Oracle/Zoho-style) | `backend/app/integrations/erp_webhook.py` |
| MQTT/IoT ingestion (Mosquitto) | `backend/app/integrations/mqtt_client.py` |

### 8. Explainability & Auditability
| Spec section | File |
|---|---|
| Structured, queryable decision log | `backend/app/explainability/logger.py` (SQLite), `frontend/src/components/ExplainabilityLog.jsx` |

## Per-file role summary (backend/app/)

- `world.py` — in-memory live scenario state (stops, vehicles, routes, road graph); the single source of truth REST/WebSocket handlers read and mutate.
- `main.py` — FastAPI app: all REST endpoints, WebSocket broadcaster, wires every layer together.
- `geometry.py` — turns a route's stop sequence into a road-following polyline (Dijkstra over the road graph, or OSRM geometry when available) for the map.
- `core/models.py` — shared domain types: `Stop`, `Vehicle`, `Depot`, `ChargingStation`, `Triage`, haversine + energy-consumption helpers.
- `optimizer/` — the mathematical core (see table above).
- `algorithms/` — classical comparison algorithms + the Arena orchestrator.
- `graph/` — road graph construction, dynamic edge weighting, partitioning, OSRM client.
- `forecasting/` — ST-GNN model, trainer, synthetic traffic generator.
- `simulation/` — SUMO network export + TraCI client (with offline fallback).
- `integrations/` — Beckn/ONDC, MQTT/IoT, ERP webhooks, Groq copilot.
- `explainability/` — SQLite-backed structured decision log.
- `benchmarks/` — Solomon/TSPLIB parsing, scalability/consistency profiler, resource monitor.

## Per-file role summary (frontend/src/)

- `App.jsx` — tabbed shell (Chaos Mode / Algorithm Arena / Profiler / Explainability Log), WebSocket wiring.
- `api.js` — REST + WebSocket client for the backend.
- `components/ChaosMap.jsx` — Leaflet map, hazard/incident placement, road-following route rendering.
- `components/AlgorithmArena.jsx` — 5-way comparison cards + convergence chart.
- `components/ParticleVisualizer.jsx` — canvas animation of real QPSO particle positions over iterations.
- `components/ProfilerDashboard.jsx` — convergence curve, Pareto front, scalability/Monte-Carlo charts.
- `components/ExplainabilityLog.jsx` — decision log feed + GenAI Copilot question box.
