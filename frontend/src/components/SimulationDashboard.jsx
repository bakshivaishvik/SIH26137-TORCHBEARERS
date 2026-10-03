import React, { useState, useEffect, useRef } from 'react';
import { SplitScreenMap } from './SplitScreenMap';
import { Reveal } from '../useReveal.jsx';
import { TextRoll } from '../primitives/TextRoll.jsx';

export const SimulationDashboard = () => {
    const [tick, setTick] = useState(0);
    const [staticWorld, setStaticWorld] = useState(null);
    const [dynamicWorld, setDynamicWorld] = useState(null);
    const [metrics, setMetrics] = useState(null);
    const [running, setRunning] = useState(false);
    const [speed, setSpeed] = useState(1);
    const [activeTool, setActiveTool] = useState('hazard'); // 'hazard' | 'order'
    const [pendingPickup, setPendingPickup] = useState(null);
    const [hazardType, setHazardType] = useState('roadblock');
    const [statusMsg, setStatusMsg] = useState('Ready. Click Play to start, or click the map to add orders/hazards.');

    useEffect(() => {
        // Connect websocket for simulation
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/sim`);

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.data) {
                    setTick(msg.data.tick || 0);
                    setStaticWorld(msg.data.static_world);
                    setDynamicWorld(msg.data.dynamic_world);
                    if (msg.data.metrics) {
                        setMetrics(msg.data.metrics);
                    }
                }
            } catch (e) {
                console.error('Error parsing sim message', e);
            }
        };

        // Auto load initial scenario on mount if not loaded
        fetch('/api/simulation/scenario/generate?num_orders=6&num_partners=3&seed=42')
            .then(res => res.json())
            .then(data => {
                if (data.data) {
                    setTick(data.data.tick || 0);
                    setStaticWorld(data.data.static_world);
                    setDynamicWorld(data.data.dynamic_world);
                    setMetrics(data.data.metrics);
                }
            })
            .catch(() => {});

        return () => ws.close();
    }, []);

    useEffect(() => {
        let interval;
        if (running) {
            const delay = Math.max(200, Math.floor(1000 / speed));
            interval = setInterval(() => {
                fetch('/api/simulation/tick', { method: 'POST' });
            }, delay);
        }
        return () => clearInterval(interval);
    }, [running, speed]);

    const handleGenerateScenario = async (scenarioName) => {
        setRunning(false);
        setPendingPickup(null);
        let seed = 42;
        let orders = 6;
        let partners = 3;

        if (scenarioName === 'gachibowli') {
            seed = 99; orders = 8; partners = 4;
            setStatusMsg('Loaded Gachibowli high-density rush (4 riders, 8 orders).');
        } else if (scenarioName === 'madhapur') {
            seed = 7; orders = 5; partners = 2;
            setStatusMsg('Loaded Madhapur fast track (2 riders, 5 orders).');
        } else {
            seed = 42; orders = 6; partners = 3;
            setStatusMsg('Loaded Hitech City peak rush (3 riders, 6 orders).');
        }

        const res = await fetch(`/api/simulation/scenario/generate?num_orders=${orders}&num_partners=${partners}&seed=${seed}`);
        const data = await res.json();
        if (data.data) {
            setTick(data.data.tick || 0);
            setStaticWorld(data.data.static_world);
            setDynamicWorld(data.data.dynamic_world);
            setMetrics(data.data.metrics);
        }
    };

    const handleReset = async () => {
        setRunning(false);
        setPendingPickup(null);
        const res = await fetch('/api/simulation/reset', { method: 'POST' });
        const data = await res.json();
        if (data.data) {
            setTick(0);
            setStaticWorld(data.data.static_world);
            setDynamicWorld(data.data.dynamic_world);
            setMetrics(data.data.metrics);
            setStatusMsg('Reset to tick 0. Riders returned to start locations.');
        }
    };

    const handleStep = async () => {
        await fetch('/api/simulation/tick', { method: 'POST' });
    };

    const handleMapClick = async (latlng) => {
        if (activeTool === 'hazard') {
            setStatusMsg(`Placed ${hazardType.replace('_', ' ')} at (${latlng.lat.toFixed(4)}, ${latlng.lng.toFixed(4)}). Dynamic QPSO immediately recalculates the detour.`);
            await fetch('/api/simulation/hazard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lat: latlng.lat, lon: latlng.lng, type: hazardType })
            });
        } else if (activeTool === 'order') {
            if (!pendingPickup) {
                setPendingPickup(latlng);
                setStatusMsg(`Pickup location set at (${latlng.lat.toFixed(4)}, ${latlng.lng.toFixed(4)}). Now click the customer location for dropoff.`);
            } else {
                setStatusMsg(`Custom order created — restaurant to customer. QPSO is inserting it into the optimal fleet schedule.`);
                await fetch('/api/simulation/order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pickup_lat: pendingPickup.lat,
                        pickup_lon: pendingPickup.lng,
                        dropoff_lat: latlng.lat,
                        dropoff_lon: latlng.lng,
                    })
                });
                setPendingPickup(null);
            }
        }
    };

    const staticM = metrics?.static || {};
    const dynamicM = metrics?.dynamic || {};
    const positions = metrics?.positions || {};

    return (
        <div className="section-stack">
            {/* Header & scenario picker */}
            <Reveal className="panel panel-accent" style={{ padding: '14px 18px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                    <div>
                        <h2 style={{ margin: 0, fontFamily: 'var(--display)', fontSize: 'var(--text-h1)', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
                            Food-delivery fleet time-lapse simulation
                        </h2>
                        <p className="panel-lede">
                            Side-by-side proof: dynamic QPSO re-optimization vs. static routing under mid-delivery roadblocks.
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                        <button onClick={() => handleGenerateScenario('hitech')} className="btn-secondary" style={{ fontSize: '11.5px', padding: '6px 11px' }}>
                            Hitech City
                        </button>
                        <button onClick={() => handleGenerateScenario('gachibowli')} className="btn-secondary" style={{ fontSize: '11.5px', padding: '6px 11px' }}>
                            Gachibowli
                        </button>
                        <button onClick={() => handleGenerateScenario('madhapur')} className="btn-secondary" style={{ fontSize: '11.5px', padding: '6px 11px' }}>
                            Madhapur
                        </button>
                    </div>
                </div>

                <div style={{ display: 'flex', gap: '18px', marginTop: '10px', paddingTop: '9px', borderTop: '1px solid var(--border-subtle)', fontSize: '11.5px', color: 'var(--text-tertiary)', flexWrap: 'wrap' }}>
                    <span><strong style={{ color: 'var(--text-secondary)' }}>1. Start</strong> — click Play to start the clock.</span>
                    <span><strong style={{ color: 'var(--text-secondary)' }}>2. Disrupt</strong> — select "Drop roadblock" and click a street.</span>
                    <span><strong style={{ color: 'var(--text-secondary)' }}>3. Compare</strong> — right map (QPSO) detours live; left map (static) stalls.</span>
                </div>
            </Reveal>

            {/* Toolbar */}
            <Reveal className="panel" delay={60} style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '10px 16px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <button
                        onClick={() => setRunning(!running)}
                        className={running ? 'btn-secondary' : 'btn-primary'}
                        style={{ padding: '7px 14px' }}
                    >
                        {running ? 'Pause' : 'Play'}
                    </button>
                    <button onClick={handleStep} disabled={running} className="btn-secondary" style={{ padding: '7px 12px' }}>
                        Step +1m
                    </button>
                    <button onClick={handleReset} className="btn-secondary" style={{ padding: '7px 12px' }}>
                        Reset
                    </button>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-tertiary)' }}>Speed</span>
                    {[1, 2, 5].map((s) => (
                        <button key={s} onClick={() => setSpeed(s)} className={`chip ${speed === s ? 'active' : ''}`}>
                            {s}x
                        </button>
                    ))}
                </div>

                <div style={{
                    background: 'var(--bg-inset)', color: 'var(--text-primary)', padding: '6px 14px', borderRadius: '5px',
                    fontFamily: 'var(--display)', fontWeight: 700, fontSize: '13px', border: '1px solid var(--border-subtle)'
                }}>
                    +{tick} min
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto' }}>
                    <span style={{ fontSize: '11.5px', color: 'var(--text-tertiary)' }}>Click action</span>
                    <button
                        onClick={() => { setActiveTool('hazard'); setPendingPickup(null); }}
                        className={`hazard-btn ${activeTool === 'hazard' ? 'active' : ''}`}
                    >
                        Drop roadblock
                    </button>
                    <button
                        onClick={() => { setActiveTool('order'); setPendingPickup(null); }}
                        className={`hazard-btn ${activeTool === 'order' ? 'active' : ''}`}
                    >
                        Add order (pickup → dropoff)
                    </button>
                </div>
            </Reveal>

            {/* Status line */}
            <TextRoll style={{ fontSize: '12px', color: 'var(--text-tertiary)', padding: '0 2px' }}>
                {statusMsg}
            </TextRoll>

            {/* Split Screen Synchronized Leaflet Maps — intentionally side-by-side,
                this is a direct live comparison, not a generic card layout. */}
            <Reveal delay={60}>
                <SplitScreenMap
                    staticWorld={staticWorld}
                    dynamicWorld={dynamicWorld}
                    positions={positions}
                    onMapClick={handleMapClick}
                    pendingPickup={pendingPickup}
                    activeTool={activeTool}
                />
            </Reveal>

            {/* Comparative scorecard — paired with the maps above by design */}
            <Reveal as="div" className="grid-2" delay={100}>
                <div className="panel panel-accent-wine">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                        <strong style={{ color: 'var(--wine-bright)', fontSize: '13px', fontWeight: 600 }}>Static baseline (traditional)</strong>
                        <span className="badge critical">{staticM.status || 'ACTIVE'}</span>
                    </div>
                    <div className="stat-row">
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Delivered</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>{staticM.delivered ?? 0}/{staticM.total_orders ?? 0}</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Late / SLA miss</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--wine-bright)' }}>{staticM.late_count ?? 0}</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Total delay</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--wine-bright)' }}>{staticM.total_duration_min ?? 0}m</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Penalty cost</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--wine-bright)' }}>₹{staticM.penalty_cost ?? 0}</div>
                        </div>
                    </div>
                </div>

                <div className="panel panel-accent">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                        <strong style={{ color: 'var(--pine-bright)', fontSize: '13px', fontWeight: 600 }}>Dynamic QPSO engine (self-healing)</strong>
                        <span className="badge standard">{dynamicM.status || 'ACTIVE'}</span>
                    </div>
                    <div className="stat-row">
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Delivered</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>{dynamicM.delivered ?? 0}/{dynamicM.total_orders ?? 0}</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Late / SLA miss</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--pine-bright)' }}>{dynamicM.late_count ?? 0}</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Total time</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--pine-bright)' }}>{dynamicM.total_duration_min ?? 0}m</div>
                        </div>
                        <div style={{ background: 'var(--bg-inset)', padding: '8px', borderRadius: '5px', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ color: 'var(--text-tertiary)', fontSize: '10.5px' }}>Saved penalty</div>
                            <div style={{ fontFamily: 'var(--display)', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--pine-bright)' }}>₹{staticM.penalty_cost ?? 0}</div>
                        </div>
                    </div>
                </div>
            </Reveal>
        </div>
    );
};
