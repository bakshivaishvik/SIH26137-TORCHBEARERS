import React, { useEffect, useState, useCallback, useRef } from "react";
import { AlertTriangle, Rocket, Swords, BarChart3, ScrollText } from "lucide-react";
import { api, connectLiveSocket } from "./api.js";
import ChaosMap from "./components/ChaosMap.jsx";
import AlgorithmArena from "./components/AlgorithmArena.jsx";
import ParticleVisualizer from "./components/ParticleVisualizer.jsx";
import ProfilerDashboard from "./components/ProfilerDashboard.jsx";
import ExplainabilityLog from "./components/ExplainabilityLog.jsx";
import { SimulationDashboard } from "./components/SimulationDashboard.jsx";
import { Reveal } from "./useReveal.jsx";
import { TextEffect } from "./primitives/TextEffect.jsx";
import { TextRoll } from "./primitives/TextRoll.jsx";
import { Dock, DockItem } from "./primitives/Dock.jsx";

const TABS = [
  { id: "chaos", label: "Chaos Mode", icon: AlertTriangle },
  { id: "simulation", label: "Simulation", icon: Rocket },
  { id: "arena", label: "Algorithm Arena", icon: Swords },
  { id: "profiler", label: "Profiler & Pareto", icon: BarChart3 },
  { id: "log", label: "Explainability Log", icon: ScrollText },
];

// Single delegated listener drives the spotlight-border glow on every
// .panel / .arena-card across the whole app (see index.css) — no per-file
// wiring needed, it just works wherever those classes appear.
function useSitewideSpotlight() {
  useEffect(() => {
    function handleMove(e) {
      const el = e.target.closest?.(".panel, .arena-card");
      if (!el) return;
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
      el.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
    }
    document.addEventListener("mousemove", handleMove, { passive: true });
    return () => document.removeEventListener("mousemove", handleMove);
  }, []);
}

export default function App() {
  const [tab, setTab] = useState("chaos");
  const [scenario, setScenario] = useState(null);
  const [connected, setConnected] = useState(false);
  const [lastHazard, setLastHazard] = useState(null);
  const [wallClockSec, setWallClockSec] = useState(null);
  const [logRefresh, setLogRefresh] = useState(0);
  const [arenaSnapshots, setArenaSnapshots] = useState(null);
  const [numVehicles, setNumVehicles] = useState(4);
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeError, setOptimizeError] = useState(null);
  const wsRef = useRef(null);

  useSitewideSpotlight();

  useEffect(() => {
    api.getScenario().then(setScenario).catch(() => {});
    const ws = connectLiveSocket((msg) => {
      setConnected(true);
      if (msg.type === "snapshot") {
        setScenario(msg.data);
      } else if (msg.type === "routes_updated") {
        setScenario((s) => (s ? { ...s, ...msg.data } : s));
        setLogRefresh((n) => n + 1);
      } else if (msg.type === "hazard_reroute") {
        setLastHazard(msg.data.hazard);
        setWallClockSec(msg.data.wall_clock_sec);
        setScenario((s) => (s ? { ...s, routes: msg.data.routes, hazards: msg.data.hazards, routes_before: msg.data.routes_before } : s));
        setLogRefresh((n) => n + 1);
      } else if (msg.type === "hazards_cleared") {
        setLastHazard(null);
        setWallClockSec(null);
        setScenario((s) => (s ? { ...s, routes: msg.data.routes, hazards: [], routes_before: [] } : s));
        setLogRefresh((n) => n + 1);
      } else if (msg.type === "incident_inserted") {
        setLogRefresh((n) => n + 1);
        api.getScenario().then(setScenario);
      }
    });
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  const runOptimize = useCallback(async () => {
    if (optimizing) return; // ignore double-clicks — a run is already in flight
    setOptimizing(true);
    setOptimizeError(null);
    try {
      const res = await api.optimize({ n_particles: 40, max_iter: 120, n_vehicles: numVehicles });
      if (res?.routes) {
        setLastHazard(null);
        setScenario((s) => (s ? { ...s, routes: res.routes, hazards: [], routes_before: [] } : s));
      }
    } catch (err) {
      setOptimizeError(err?.message || "Optimize request failed — is the backend running?");
    } finally {
      setOptimizing(false);
    }
  }, [numVehicles, optimizing]);

  return (
    <div className="app-shell app-shell-docked">
      <header className="app-header">
        <div className="brand">
          <TextEffect as="span" per="char" className="title" delay={0.1}>
            QPSO Ambulance Fleet Router
          </TextEffect>
          <span className="subtitle">SIH 2026 · Quantum-Inspired Route Optimization</span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <label className="fleet-select">
            <span>Fleet</span>
            <select value={numVehicles} onChange={(e) => setNumVehicles(Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 8].map((v) => (
                <option key={v} value={v}>
                  {v} vehicle{v > 1 ? "s" : ""}
                </option>
              ))}
            </select>
          </label>
          <button className="btn-secondary" onClick={runOptimize} disabled={optimizing}>
            <TextRoll as="span">{optimizing ? "Optimizing… (can take ~30–90s)" : "Run full optimize()"}</TextRoll>
          </button>
          <div className="status-pill">
            <span className={`status-dot ${connected ? "connected" : ""}`} />
            {connected ? "live" : "disconnected"}
          </div>
        </div>
      </header>

      {optimizeError && (
        <div className="error-banner">
          <span>{optimizeError}</span>
          <button className="error-banner-dismiss" onClick={() => setOptimizeError(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      <main className="main-area main-area-docked">
        {tab === "simulation" && (
          <div className="panel" style={{ height: "calc(100vh - 150px)", overflow: "auto" }}>
            <SimulationDashboard />
          </div>
        )}

        {tab === "chaos" && (
          <div className="section-stack">
            <Reveal className="panel">
              <ChaosMap scenario={scenario} lastHazard={lastHazard} wallClockSec={wallClockSec} />
            </Reveal>
            <Reveal className="panel" delay={80}>
              <p className="panel-title">Active routes ({scenario?.routes?.length || 0})</p>
              {(scenario?.routes || []).map((r, idx) => (
                <div
                  className="route-row stagger-item"
                  style={{ "--i": idx }}
                  key={r.vehicle_id + "-" + r.stop_sequence.join(",")}
                >
                  <span>vehicle {r.vehicle_id}</span>
                  <span>{r.stop_sequence.join(" → ")}</span>
                  <span>{r.cost?.toFixed(1)}</span>
                </div>
              ))}
              {(!scenario?.routes || scenario.routes.length === 0) && (
                <div className="empty-state">
                  <p className="empty-title">No routes yet</p>
                  <p className="empty-body">Click "Run full optimize()" above to compute the fleet's initial routes.</p>
                </div>
              )}
            </Reveal>
          </div>
        )}

        {tab === "arena" && (
          <div className="section-stack">
            <AlgorithmArena onResults={setArenaSnapshots} />
            <Reveal className="panel" delay={80}>
              <p className="panel-title">Particle State Visualizer</p>
              <ParticleVisualizer snapshots={arenaSnapshots} />
            </Reveal>
          </div>
        )}

        {tab === "profiler" && (
          <ProfilerDashboard convergenceHistory={scenario?.convergence_history} paretoFront={scenario?.pareto_front} />
        )}

        {tab === "log" && <ExplainabilityLog refreshTrigger={logRefresh} />}
      </main>

      <div className="dock-dock">
        <Dock>
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <DockItem key={t.id} active={tab === t.id} label={t.label} onClick={() => setTab(t.id)}>
                <Icon size={20} strokeWidth={2} />
              </DockItem>
            );
          })}
        </Dock>
      </div>
    </div>
  );
}
