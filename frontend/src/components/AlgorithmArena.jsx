import React, { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, Cell } from "recharts";
import { api } from "../api.js";
import { Reveal } from "../useReveal.jsx";
import { AnimatedBackground } from "../primitives/AnimatedBackground.jsx";
import { TextRoll } from "../primitives/TextRoll.jsx";

const ALGO_META = {
  qubit_qpso: { label: "Q-QPSO (qubit & rotation gate)", color: "#a34456", tech: "Qubit matrix |α|²+|β|²=1 · R_y(Δθ) gate" },
  qpso: { label: "Delta-QPSO (quantum-behaved)", color: "#3a8f6b", tech: "Wavepacket tunneling · no velocity vector" },
  standard_pso: { label: "Standard PSO", color: "#5b8fb0", tech: "Velocity vector (w, c1, c2)" },
  genetic_algorithm: { label: "Genetic algorithm", color: "#c08a3e", tech: "Crossover & mutation" },
  gwo: { label: "Grey wolf optimizer", color: "#8f8e8a", tech: "Alpha / beta / delta wolves" },
  dijkstra: { label: "Dijkstra / A*", color: "#55565b", tech: "Greedy shortest path" },
};

const CHART_TOOLTIP_STYLE = {
  background: "var(--bg-surface-raised)",
  border: "1px solid var(--border-default)",
  borderRadius: 6,
  color: "var(--text-primary)",
  fontSize: 12,
};

export default function AlgorithmArena({ onResults }) {
  const [results, setResults] = useState(null);
  const [running, setRunning] = useState(false);
  const [nAgents, setNAgents] = useState(40);
  const [maxIter, setMaxIter] = useState(120);

  async function run() {
    setRunning(true);
    try {
      const res = await api.runArena({ n_agents: nAgents, max_iter: maxIter, seed: Date.now() % 1000 });
      setResults(res);
      if (onResults) onResults(res.qpso?.particle_snapshots || null);
    } finally {
      setRunning(false);
    }
  }

  const convergenceKeys = ["qubit_qpso", "qpso", "standard_pso", "gwo", "genetic_algorithm"];
  let chartData = [];
  let barComparison = [];
  let bestAlgo = "qpso";
  let qpsoCost = 0;
  let psoCost = 0;
  let psoDeltaPct = "0";

  if (results) {
    const maxLen = Math.max(...convergenceKeys.map((k) => (results[k]?.convergence_history || []).length));
    chartData = Array.from({ length: maxLen }, (_, i) => {
      const row = { iter: i + 1 };
      convergenceKeys.forEach((k) => {
        const hist = results[k]?.convergence_history || [];
        if (hist.length > 0) {
          row[k] = Number((hist[Math.min(i, hist.length - 1)]).toFixed(1));
        }
      });
      return row;
    });

    barComparison = convergenceKeys.map((k) => ({
      name: ALGO_META[k].label,
      key: k,
      cost: results[k]?.cost != null ? Number(results[k].cost.toFixed(1)) : 999,
      time_ms: results[k]?.time_sec != null ? Number((results[k].time_sec * 1000).toFixed(1)) : 0,
      color: ALGO_META[k].color,
    })).sort((a, b) => a.cost - b.cost);

    if (barComparison.length > 0) bestAlgo = barComparison[0].key;

    qpsoCost = results.qpso?.cost || 0;
    psoCost = results.standard_pso?.cost || 0;
    if (psoCost > 0 && qpsoCost > 0) {
      psoDeltaPct = (((psoCost - qpsoCost) / psoCost) * 100).toFixed(1);
    }
  }

  return (
    <div className="section-stack">
      <Reveal className="panel panel-accent">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 style={{ margin: 0, fontFamily: "var(--display)", fontSize: "var(--text-h1)", fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text-primary)" }}>
              5-way metaheuristic &amp; graph optimization arena
            </h3>
            <p className="panel-lede">
              Benchmarks QPSO's delta-well tunneling against classical PSO, GA, GWO, and Dijkstra.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
              <span>Swarm size</span>
              <select value={nAgents} onChange={(e) => setNAgents(Number(e.target.value))}>
                <option value={20}>20 agents</option>
                <option value={40}>40 agents</option>
                <option value={60}>60 agents</option>
              </select>
            </label>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
              <span>Iterations</span>
              <select value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))}>
                <option value={60}>60</option>
                <option value={120}>120</option>
                <option value={200}>200</option>
              </select>
            </label>
            <button className="btn-primary" onClick={run} disabled={running}>
              <TextRoll as="span">{running ? "Computing…" : "Run head-to-head arena"}</TextRoll>
            </button>
          </div>
        </div>

        <div className="grid-3" style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border-subtle)" }}>
          <div>
            <div style={{ color: "var(--pine-bright)", fontWeight: 600, fontSize: 12 }}>Quantum wavepacket superposition</div>
            <div style={{ color: "var(--text-tertiary)", fontSize: 11.5, marginTop: 3, lineHeight: 1.5 }}>
              Particles occupy a quantum state space, tunneling through high-cost barriers where standard PSO stalls.
            </div>
          </div>
          <div>
            <div style={{ color: "var(--text-secondary)", fontWeight: 600, fontSize: 12 }}>Zero velocity-vector clamping</div>
            <div style={{ color: "var(--text-tertiary)", fontSize: 11.5, marginTop: 3, lineHeight: 1.5 }}>
              No empirical tuning of inertia or acceleration coefficients — governed by a single contraction-expansion parameter α.
            </div>
          </div>
          <div>
            <div style={{ color: "var(--amber)", fontWeight: 600, fontSize: 12 }}>100% feasibility, delta re-opt</div>
            <div style={{ color: "var(--text-tertiary)", fontSize: 11.5, marginTop: 3, lineHeight: 1.5 }}>
              SPV continuous-to-discrete mapping guarantees every state projects into a valid permutation with zero SLA violations.
            </div>
          </div>
        </div>
      </Reveal>

      {results && (
        <Reveal as="div" className="arena-grid">
          <AnimatedBackground enableHover transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}>
          {Object.keys(ALGO_META).map((k, idx) => {
            const r = results[k];
            if (!r) return null;
            const meta = ALGO_META[k];
            const isWinner = k === bestAlgo;

            return (
              <div key={k} data-id={k} className={`arena-card stagger-item ${isWinner ? "winner" : ""}`} style={{ "--i": idx }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <span className="algo-name" style={{ color: meta.color }}>{meta.label}</span>
                  </div>
                  {isWinner && (
                    <span style={{ background: "var(--pine-wash)", color: "var(--pine-bright)", fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4, border: "1px solid var(--pine-bright)" }}>
                      WINNER
                    </span>
                  )}
                </div>

                <div style={{ marginTop: 8, display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span className="algo-cost" style={{ color: isWinner ? "var(--pine-bright)" : "var(--text-primary)" }}>
                    {r.cost != null ? r.cost.toFixed(1) : "—"}
                  </span>
                  <span style={{ fontSize: 11.5, color: "var(--text-tertiary)" }}>cost units</span>
                </div>

                <div style={{ marginTop: 8, padding: "7px 9px", background: "var(--bg-inset)", borderRadius: 5, fontSize: 11.5 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-tertiary)" }}>
                    <span>Runtime</span>
                    <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{r.time_sec != null ? `${(r.time_sec * 1000).toFixed(1)} ms` : "N/A"}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-tertiary)", marginTop: 4 }}>
                    <span>Feasibility</span>
                    <strong style={{ color: r.feasible ? "var(--pine-bright)" : "var(--wine-bright)", fontWeight: 600 }}>{r.feasible ? "100% feasible" : "Infeasible"}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-tertiary)", marginTop: 4 }}>
                    <span>Mechanism</span>
                    <span style={{ color: "var(--text-tertiary)", fontSize: 10.5 }}>{meta.tech}</span>
                  </div>
                </div>

                {k === "qpso" && psoCost > 0 && (
                  <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--pine-bright)", fontWeight: 600, background: "var(--pine-wash)", padding: "4px 8px", borderRadius: 4, textAlign: "center" }}>
                    {psoDeltaPct}% lower cost than standard PSO
                  </div>
                )}
              </div>
            );
          })}
          </AnimatedBackground>
        </Reveal>
      )}

      {results && (
        <div className="section-stack">
          <Reveal className="panel" delay={60}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <p className="panel-title" style={{ margin: 0 }}>Convergence curve — fitness vs. iteration</p>
              <span style={{ fontSize: 11, color: "var(--pine-bright)", fontWeight: 600 }}>QPSO tunnels to the optimum faster</span>
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" />
                <XAxis dataKey="iter" stroke="var(--text-tertiary)" fontSize={11} label={{ value: "Iteration", position: "insideBottomRight", offset: -5, fill: "var(--text-tertiary)", fontSize: 11 }} />
                <YAxis stroke="var(--text-tertiary)" fontSize={11} label={{ value: "Objective cost", angle: -90, position: "insideLeft", fill: "var(--text-tertiary)", fontSize: 11 }} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: 10 }} />
                {convergenceKeys.map((k) => (
                  <Line
                    key={k}
                    type="monotone"
                    dataKey={k}
                    name={ALGO_META[k].label}
                    stroke={ALGO_META[k].color}
                    dot={false}
                    strokeWidth={k === "qpso" ? 2.5 : 1.5}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </Reveal>

          <Reveal className="panel" delay={100}>
            <p className="panel-title" style={{ margin: "0 0 10px 0" }}>Final cost comparison</p>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={barComparison} layout="vertical" margin={{ top: 10, right: 30, left: 30, bottom: 0 }}>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" />
                <XAxis type="number" stroke="var(--text-tertiary)" fontSize={11} />
                <YAxis type="category" dataKey="name" stroke="var(--text-tertiary)" fontSize={11} width={110} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Bar dataKey="cost" name="Total cost" radius={[0, 3, 3, 0]}>
                  {barComparison.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Reveal>
        </div>
      )}
    </div>
  );
}
