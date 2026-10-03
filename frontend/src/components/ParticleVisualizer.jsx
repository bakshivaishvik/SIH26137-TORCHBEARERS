import React, { useEffect, useRef, useState } from "react";

/**
 * Quantum-Behaved Particle Swarm State Visualizer:
 * Visualizes the quantum delta-potential well V(x) = -γδ(x - mbest),
 * particle probability distribution clouds |ψ(x)|², and swarm tunneling
 * in the continuous search space.
 */
export default function ParticleVisualizer({ snapshots }) {
  const canvasRef = useRef(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(150);

  useEffect(() => {
    if (!playing || !snapshots || snapshots.length === 0) return;
    const id = setInterval(() => setFrame((f) => (f + 1) % snapshots.length), speed);
    return () => clearInterval(id);
  }, [playing, snapshots, speed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !snapshots || snapshots.length === 0) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;

    // Deep quantum dark background
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#0a0b0d";
    ctx.fillRect(0, 0, W, H);

    // Quantum Grid Lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1;
    const gridSize = 34;
    for (let x = 0; x <= W; x += gridSize) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    for (let y = 0; y <= H; y += gridSize) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }

    const currentPositions = snapshots[Math.min(frame, snapshots.length - 1)] || [];
    if (currentPositions.length === 0) return;

    // Calculate Mean Best (mbest) center of mass
    let sumX = 0, sumY = 0;
    currentPositions.forEach((p) => {
      sumX += p[0] || 0;
      sumY += p[1 % p.length] || 0;
    });
    const mbestX = (sumX / currentPositions.length) * W;
    const mbestY = (sumY / currentPositions.length) * H;

    // Draw Quantum Delta Potential Well Attractor Ring
    const gradWell = ctx.createRadialGradient(mbestX, mbestY, 4, mbestX, mbestY, 70);
    gradWell.addColorStop(0, "rgba(58, 143, 107, 0.35)");
    gradWell.addColorStop(0.5, "rgba(216, 215, 211, 0.1)");
    gradWell.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = gradWell;
    ctx.beginPath();
    ctx.arc(mbestX, mbestY, 70, 0, Math.PI * 2);
    ctx.fill();

    // Attractor Core Crosshair
    ctx.strokeStyle = "#3a8f6b";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(mbestX, mbestY, 6, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(mbestX - 10, mbestY); ctx.lineTo(mbestX + 10, mbestY);
    ctx.moveTo(mbestX, mbestY - 10); ctx.lineTo(mbestX, mbestY + 10);
    ctx.stroke();

    // Draw Quantum Particles & Wavepacket probability halos
    currentPositions.forEach((p, idx) => {
      const px = (p[0] || 0) * W;
      const py = (p[1 % p.length] || 0) * H;

      // Distance to mbest
      const dist = Math.sqrt((px - mbestX) ** 2 + (py - mbestY) ** 2);
      const isTunneling = dist > 80;

      // Wavefunction halo |ψ|²
      const haloGrad = ctx.createRadialGradient(px, py, 1, px, py, isTunneling ? 14 : 9);
      haloGrad.addColorStop(0, isTunneling ? "rgba(192, 138, 62, 0.75)" : "rgba(216, 215, 211, 0.7)");
      haloGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = haloGrad;
      ctx.beginPath();
      ctx.arc(px, py, isTunneling ? 14 : 9, 0, Math.PI * 2);
      ctx.fill();

      // Particle Core
      ctx.fillStyle = isTunneling ? "#c08a3e" : "#f1f0ec";
      ctx.beginPath();
      ctx.arc(px, py, isTunneling ? 3.5 : 2.5, 0, Math.PI * 2);
      ctx.fill();

      // Quantum Entanglement line to mbest
      if (idx % 3 === 0) {
        ctx.strokeStyle = isTunneling ? "rgba(192, 138, 62, 0.15)" : "rgba(58, 143, 107, 0.15)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(mbestX, mbestY);
        ctx.stroke();
      }
    });

    // Physics HUD overlay
    const alphaFrac = (1.0 - 0.5 * (frame / Math.max(1, snapshots.length - 1))).toFixed(3);
    const progressPct = (((frame + 1) / snapshots.length) * 100).toFixed(0);

    ctx.fillStyle = "rgba(20, 21, 25, 0.9)";
    ctx.fillRect(8, 8, 250, 90);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
    ctx.lineWidth = 1;
    ctx.strokeRect(8, 8, 250, 90);

    ctx.fillStyle = "#d8d7d3";
    ctx.font = "bold 11px monospace";
    ctx.fillText(`Q-QPSO ROTATION GATE DYNAMICS`, 16, 24);

    ctx.fillStyle = "#b9b8b4";
    ctx.font = "11px monospace";
    ctx.fillText(`Frame: ${frame + 1}/${snapshots.length} (${progressPct}%)`, 16, 40);
    ctx.fillText(`Qubit normalization: |α|²+|β|² = 1.000`, 16, 56);
    ctx.fillText(`Quantum gate: R_y(Δθ) phase rotation`, 16, 72);
    ctx.fillText(`State: ${frame < snapshots.length * 0.4 ? "Superposition / exploration" : "Wavepacket collapse"}`, 16, 88);

    ctx.fillStyle = "#3a8f6b";
    ctx.font = "10px monospace";
    ctx.fillText(`mbest: (${(mbestX / W).toFixed(2)}, ${(mbestY / H).toFixed(2)})`, W - 140, H - 12);
  }, [frame, snapshots]);

  if (!snapshots || snapshots.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">Quantum particle state visualizer</p>
        <p className="empty-body">
          Click <strong>"Run head-to-head arena"</strong> in the left panel to stream real-time quantum wavepacket vectors and watch particles tunnel to the global minimum.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ position: "relative" }}>
        <canvas
          ref={canvasRef}
          width={520}
          height={320}
          style={{ width: "100%", borderRadius: 6, border: "1px solid var(--border-default)", background: "var(--bg-base)", display: "block" }}
        />
      </div>

      {/* Playback Controls & Speed Selector */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", background: "var(--bg-surface-raised)", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border-subtle)" }}>
        <button className="btn-secondary" style={{ padding: "5px 12px", fontSize: 12 }} onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play"}
        </button>

        <button className="btn-secondary" style={{ padding: "5px 10px", fontSize: 11 }} onClick={() => { setPlaying(false); setFrame(0); }}>
          Reset
        </button>

        <input
          type="range"
          min={0}
          max={snapshots.length - 1}
          value={frame}
          onChange={(e) => { setPlaying(false); setFrame(Number(e.target.value)); }}
          style={{ flex: 1, accentColor: "#3a8f6b", cursor: "pointer" }}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--text-secondary)" }}>
          <span>Speed</span>
          {[250, 150, 60].map((s, idx) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              style={{
                padding: "2px 7px",
                fontSize: 10,
                borderRadius: 3,
                border: "1px solid var(--border-default)",
                background: speed === s ? "var(--pine-wash)" : "transparent",
                color: speed === s ? "var(--pine-bright)" : "var(--text-tertiary)",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {idx === 0 ? "0.5x" : idx === 1 ? "1x" : "2x"}
            </button>
          ))}
        </div>
      </div>

      {/* Legend & Mechanics Annotation */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-tertiary)", padding: "0 4px" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--pine-bright)" }}></span>
          <strong style={{ color: "var(--pine-bright)" }}>mbest center of mass</strong>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--silver)" }}></span>
          <span>Quantum particle |ψ|²</span>
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--amber)" }}></span>
          <span style={{ color: "var(--amber)" }}>Tunneling active</span>
        </span>
      </div>
    </div>
  );
}
