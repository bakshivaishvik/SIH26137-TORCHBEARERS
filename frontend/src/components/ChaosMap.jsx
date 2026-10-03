import React, { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Popup, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { api } from "../api.js";
import { snapRouteToRoads } from "../roadSnap.js";
import { TextRoll } from "../primitives/TextRoll.jsx";

const TRIAGE_COLOR = { 1: "#a34456", 2: "#c08a3e", 3: "#3a8f6b", 4: "#83827e" };
const ROUTE_COLORS = ["#3a8f6b", "#8f8e8a", "#c08a3e", "#5b8fb0", "#a34456", "#6b8f7a"];
const REROUTE_COLOR = "#3a8f6b";

const HAZARD_TYPES = [
  { id: "roadblock", label: "Roadblock" },
  { id: "accident", label: "Accident" },
  { id: "damaged_road", label: "Damaged road" },
  { id: "event_closure", label: "Event closure" },
];

// Uber-style solid pin markers, built from inline SVG rather than emoji.
const depotIcon = L.divIcon({
  className: "",
  html: `<div style="width:12px;height:12px;border-radius:3px;background:#d8d7d3;border:2px solid #0a0b0d;box-shadow:0 1px 4px rgba(0,0,0,0.5);"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function pinSvg(fill) {
  return `<svg width="22" height="30" viewBox="0 0 22 30" xmlns="http://www.w3.org/2000/svg" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,0.5));">
    <path d="M11 0C4.9 0 0 4.9 0 11c0 8.25 11 19 11 19s11-10.75 11-19c0-6.1-4.9-11-11-11z" fill="${fill}"/>
    <circle cx="11" cy="11" r="4" fill="#0a0b0d" opacity="0.55"/>
  </svg>`;
}

const createHazardIcon = () =>
  L.divIcon({
    className: "",
    html: pinSvg("#a34456"),
    iconSize: [22, 30],
    iconAnchor: [11, 30],
  });

function ClickHandler({ onClick }) {
  useMapEvents({ click(e) { onClick(e.latlng); } });
  return null;
}

/** Builds the depot->stops->depot waypoint list a route's polyline should follow. */
function buildWaypoints(route, depot, stopsById) {
  if (Array.isArray(route.geometry) && route.geometry.length > 1) return route.geometry;
  if (route.geometry && route.geometry.coordinates) {
    return route.geometry.coordinates.map((c) => [c[1], c[0]]);
  }
  if (!depot) return [];
  return [
    [depot.lat, depot.lon],
    ...route.stop_sequence.map((sid) => {
      const s = stopsById[sid];
      return s ? [s.lat, s.lon] : null;
    }).filter(Boolean),
    [depot.lat, depot.lon],
  ];
}

export default function ChaosMap({ scenario, lastHazard, wallClockSec }) {
  const [hazardType, setHazardType] = useState("roadblock");
  const [algorithmType, setAlgorithmType] = useState("qubit_qpso"); // "qubit_qpso" | "delta_qpso"
  const [insertMode, setInsertMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mapError, setMapError] = useState(null);
  const [roadGeoms, setRoadGeoms] = useState({});
  const mountedRef = useRef(true);

  const depot = scenario?.depot;
  const stops = scenario?.stops;
  const routes = scenario?.routes;
  const stopsById = Object.fromEntries((stops || []).map((s) => [s.id, s]));

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // Snap each route's stop-to-stop waypoints onto real streets for display,
  // purely client-side — the optimizer's own cost/time numbers are untouched.
  useEffect(() => {
    if (!depot || !routes || routes.length === 0) return;
    routes.forEach((r) => {
      const waypoints = buildWaypoints(r, depot, stopsById);
      if (waypoints.length < 2) return;
      const key = `${r.vehicle_id}-${r.stop_sequence.join(",")}`;
      snapRouteToRoads(waypoints).then((snapped) => {
        if (!snapped || !mountedRef.current) return;
        setRoadGeoms((prev) => (prev[key] === snapped ? prev : { ...prev, [key]: snapped }));
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depot, JSON.stringify((routes || []).map((r) => [r.vehicle_id, r.stop_sequence]))]);

  if (!scenario) {
    return (
      <div>
        <p style={{ fontSize: 12.5, color: "var(--text-tertiary)", marginBottom: 10 }}>Loading scenario…</p>
        <div className="skeleton-map" />
      </div>
    );
  }

  const center = [depot?.lat ?? 12.9716, depot?.lon ?? 77.5946];
  const allHazards = scenario.hazards || [];
  const hazardIcon = createHazardIcon();

  async function handleMapClick(latlng) {
    if (busy) return; // ignore clicks while a reroute is already in flight
    setBusy(true);
    setMapError(null);
    try {
      if (insertMode) {
        await api.insertIncident({ lat: latlng.lat, lon: latlng.lng, triage: "CRITICAL", sla_response_min: 20 });
      } else {
        await api.placeHazard({ lat: latlng.lat, lon: latlng.lng, hazard_type: hazardType, algorithm_type: algorithmType });
      }
    } catch (err) {
      setMapError(err?.message || "Hazard placement failed — backend may be slow or unreachable.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClearHazards() {
    if (busy) return;
    setBusy(true);
    setMapError(null);
    try {
      await api.clearHazards();
    } catch (err) {
      setMapError(err?.message || "Clear hazards failed — backend may be slow or unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="hazard-toolbar">
        {HAZARD_TYPES.map((h) => (
          <button
            key={h.id}
            className={`hazard-btn ${!insertMode && hazardType === h.id ? "active" : ""}`}
            disabled={busy}
            onClick={() => { setHazardType(h.id); setInsertMode(false); }}
          >
            {h.label}
          </button>
        ))}
        <button className={`hazard-btn ${insertMode ? "active" : ""}`} disabled={busy} onClick={() => setInsertMode(true)}>
          + New incident
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 6, paddingLeft: 10, borderLeft: "1px solid var(--border-subtle)" }}>
          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Algorithm</span>
          <select value={algorithmType} onChange={(e) => setAlgorithmType(e.target.value)} disabled={busy} style={{ fontSize: 11.5, padding: "5px 8px" }}>
            <option value="qubit_qpso">Q-QPSO (qubit &amp; rotation gate)</option>
            <option value="delta_qpso">Delta-QPSO (potential well)</option>
          </select>
        </div>
        {allHazards.length > 0 && (
          <button
            className="hazard-btn"
            disabled={busy}
            style={{ borderColor: "var(--wine-bright)", color: "var(--wine-bright)" }}
            onClick={handleClearHazards}
          >
            Clear hazards ({allHazards.length})
          </button>
        )}
        <TextRoll className="chaos-status" style={{ marginLeft: "auto", fontSize: 12, color: busy ? "var(--amber)" : "var(--text-tertiary)" }}>
          {busy
            ? `computing reroute with ${algorithmType === "qubit_qpso" ? "Q-QPSO" : "Delta-QPSO"}… (slower without a live OSRM container)`
            : wallClockSec != null
            ? `last reroute: ${(wallClockSec * 1000).toFixed(1)} ms`
            : "click the map to place a hazard"}
        </TextRoll>
      </div>

      {mapError && (
        <div style={{ marginBottom: 10, padding: "8px 12px", background: "var(--wine-wash)", border: "1px solid var(--wine-bright)", borderRadius: "var(--radius-sm)", color: "var(--wine-bright)", fontSize: 12 }}>
          {mapError}
        </div>
      )}

      <div className="map-wrap">
        <MapContainer center={center} zoom={13} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            className="map-tiles-dark"
          />
          <ClickHandler onClick={handleMapClick} />
          {depot && <Marker position={[depot.lat, depot.lon]} icon={depotIcon}><Popup>Depot (HQ)</Popup></Marker>}
          {(stops || []).map((s) => (
            <CircleMarker key={s.id} center={[s.lat, s.lon]} radius={5.5}
              pathOptions={{ color: TRIAGE_COLOR[s.triage] || "#8f8e8a", weight: 2, fillOpacity: 0.9 }}>
              <Popup>Incident #{s.id} · triage {s.triage}</Popup>
            </CircleMarker>
          ))}
          {allHazards.map((h, i) => (
            <Marker key={`hazard-${i}-${h.lat}-${h.lon}`} position={[h.lat, h.lon]} icon={hazardIcon}>
              <Popup>
                <strong>Active disruption — {h.type.replace("_", " ")}</strong><br />
                {h.lat.toFixed(4)}, {h.lon.toFixed(4)}<br />
                Traffic penalty applied; QPSO re-routed active vehicles.
              </Popup>
            </Marker>
          ))}
          {(routes || []).map((r, idx) => {
            const key = `${r.vehicle_id}-${r.stop_sequence.join(",")}`;
            const pts = roadGeoms[key] || buildWaypoints(r, depot, stopsById);

            const isRerouted = r.is_rerouted || allHazards.length > 0;
            const routeColor = isRerouted ? REROUTE_COLOR : ROUTE_COLORS[r.vehicle_id % ROUTE_COLORS.length];
            const routeWeight = isRerouted ? 4.5 : 3.5;

            return (
              <Polyline
                key={`route-${r.vehicle_id}-${idx}-${allHazards.length}`}
                positions={pts}
                pathOptions={{ color: routeColor, weight: routeWeight, opacity: 0.92, lineJoin: "round", lineCap: "round" }}
              >
                <Popup>
                  <strong>{isRerouted ? "Active QPSO detour route" : `Vehicle #${r.vehicle_id} route`}</strong><br />
                  Stops: {r.stop_sequence.join(" → ")}<br />
                  Cost: {r.cost ? r.cost.toFixed(1) : "N/A"}
                </Popup>
              </Polyline>
            );
          })}
        </MapContainer>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 18, marginTop: 10, padding: "8px 4px", fontSize: 11.5, color: "var(--text-tertiary)" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ display: "inline-block", width: 14, height: 3, background: REROUTE_COLOR, borderRadius: 2 }} />
          Live QPSO route
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--wine-bright)" }} />
          Active hazard
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--amber)" }} />
          Incident stop
        </span>
      </div>
    </div>
  );
}
