# QPSO-Driven Smart-City Ambulance Fleet Router

A quantum-inspired metaheuristic (QPSO) routing platform for an ambulance
fleet: mathematical core, predictive AI layer, simulation, live disruption
UI, benchmarking suite, and real-world system integrations, wired end to
end. Built for AICTE Smart India Hackathon 2026, Quantum Technology
Vertical, Problem Statement 1 (Egreen Quanta).

## What's real vs. what's mocked, honestly

Everything in this repo is real, runnable code — no empty stub functions.
A few pieces run against **local mocks / offline fallbacks** rather than
live production services, because those need external accounts, hardware,
or heavy installs this environment can't provide. Each one is a one-line
config change away from the real thing:

| Component | Runs against | Swap to production by |
|---|---|---|
| OSRM distance matrix | haversine fallback if container isn't up | starting the `osrm` docker-compose service with a real `.osrm` dataset |
| SUMO traffic sim | offline synthetic-flow replay | installing SUMO + running `sumo -c city.sumocfg`, flip `TraCIBridge(offline=False)` |
| ONDC/Beckn registry | local mock server (`beckn_mock_server.py`) | set `BECKN_BASE_URL` to the real gateway |
| Groq LLM Copilot | disabled until `GROQ_API_KEY` is set | export the key |
| ST-GNN forecaster | trained on realistic synthetic traffic tensors | point `synthetic_traffic.py`'s generator at real/SUMO-exported time-series |

The **mathematical core (QPSO/SPV/Prins' Split/Pareto/repair/delta-reopt),
the 5-way Algorithm Arena, the FastAPI backend, and the React UI are fully
live** — see `smoke_test.py` for a script that proves the whole
hazard→reroute→log loop end to end against a running backend.

## Quick start (Linux/macOS)

```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# in another terminal
cd frontend && npm install && npm run dev
```
Open http://localhost:5173. For Windows, see `RUN_INSTRUCTIONS_WINDOWS.md`.

## Full stack via Docker

```bash
docker compose up --build
```
Brings up OSRM, Mosquitto, a local Beckn/ONDC mock, the FastAPI backend,
and the React frontend. Open http://localhost:5173.

## Smoke test

```bash
python smoke_test.py --base-url http://localhost:8000
```
Exercises: health check → scenario reset → full QPSO optimize() → place a
hazard (Chaos Mode) → confirm localized delta re-optimization completed in
under 5s → confirm an explainability log entry was written → dynamic
incident insertion → 5-way Algorithm Arena run.

## Unit tests

```bash
cd backend && pytest tests/ -v
```

## Where each hackathon requirement lives

See `ARCHITECTURE.md` for the full section-to-file mapping.

## Tech stack

Python (NumPy, FastAPI, WebSockets) for the optimizer core and backend;
PyTorch (manual graph-convolution, documented PyG swap point) for the
ST-GNN; NetworkX/OSMnx for the road graph; OSRM for distance matrices;
SUMO/TraCI for simulation; Eclipse Mosquitto/paho-mqtt for IoT telemetry;
Groq for the LLM copilot; Beckn Protocol for ONDC; React + Leaflet +
Recharts for the frontend.
