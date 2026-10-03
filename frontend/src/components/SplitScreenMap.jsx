import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { snapRouteToRoads } from '../roadSnap.js';

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTR = '&copy; OpenStreetMap contributors';

const syncMaps = (map1, map2) => {
    let isSyncing = false;
    map1.on('move', () => {
        if (!isSyncing && map2) {
            isSyncing = true;
            map2.setView(map1.getCenter(), map1.getZoom(), { animate: false });
            isSyncing = false;
        }
    });
    map2.on('move', () => {
        if (!isSyncing && map1) {
            isSyncing = true;
            map1.setView(map2.getCenter(), map2.getZoom(), { animate: false });
            isSyncing = false;
        }
    });
};

// Small solid dot marker, Uber-style, with an optional label chip.
const createDotIcon = (color, label = '') => L.divIcon({
    className: '',
    html: `<div style="display:flex;align-items:center;gap:5px;transform:translate(-50%,-50%);">
        <span style="width:11px;height:11px;border-radius:50%;background:${color};border:2px solid #0a0b0d;box-shadow:0 1px 4px rgba(0,0,0,0.5);display:block;"></span>
        ${label ? `<span style="background:#1b1d22;color:#f1f0ec;padding:2px 6px;border-radius:4px;font-size:10.5px;font-weight:600;white-space:nowrap;border:1px solid rgba(255,255,255,0.12);">${label}</span>` : ''}
    </div>`,
    iconSize: [11, 11],
    iconAnchor: [6, 6],
});

const createVehicleIcon = (color, label = '', blocked = false) => L.divIcon({
    className: '',
    html: `<div style="display:flex;align-items:center;gap:5px;transform:translate(-50%,-50%);">
        <span style="width:13px;height:13px;border-radius:4px;background:${color};border:2px solid #0a0b0d;box-shadow:0 1px 4px rgba(0,0,0,0.5);display:block;${blocked ? 'outline:2px solid #a34456;outline-offset:1px;' : ''}"></span>
        ${label ? `<span style="background:#1b1d22;color:#f1f0ec;padding:2px 6px;border-radius:4px;font-size:10.5px;font-weight:600;white-space:nowrap;border:1px solid rgba(255,255,255,0.12);">${label}</span>` : ''}
    </div>`,
    iconSize: [13, 13],
    iconAnchor: [7, 7],
    zIndexOffset: 1000,
});

const ROUTE_COLORS = ['#5b8fb0', '#3a8f6b', '#c08a3e', '#8f8e8a', '#a34456', '#6b8f7a'];

const renderWorld = (map, world, positions, mode) => {
    if (!map || !world) return;

    // Clear old layers except TileLayer
    map.eachLayer((layer) => {
        if (layer instanceof L.Polyline || layer instanceof L.Marker || layer instanceof L.CircleMarker) {
            map.removeLayer(layer);
        }
    });

    // 1. Depot / hub
    if (world.depot) {
        L.marker([world.depot.lat, world.depot.lon], {
            icon: createDotIcon('#d8d7d3', 'Hub')
        }).bindPopup('<strong>Central depot / kitchen hub</strong>').addTo(map);
    }

    // 2. Stops (pickups & dropoffs)
    (world.stops || []).forEach((s) => {
        const isPickup = s.stop_type === 'PICKUP';
        const isDelivered = s.status === 'DELIVERED';
        const isCollected = s.status === 'COLLECTED';
        const color = isDelivered ? '#3a8f6b' : isCollected ? '#c08a3e' : isPickup ? '#5b8fb0' : '#8f8e8a';
        const label = `${s.order_id || s.id} · ${(s.status || 'pending').toLowerCase()}`;

        L.marker([s.lat, s.lon], { icon: createDotIcon(color, label) }).bindPopup(`
            <strong>${isPickup ? 'Restaurant / pickup' : 'Customer / dropoff'}</strong><br/>
            Order: ${s.order_id || s.id}<br/>
            Status: <span style="font-weight:600;">${s.status || 'PENDING'}</span>
        `).addTo(map);
    });

    // 3. Hazards
    (world.hazards || []).forEach((h) => {
        L.marker([h.lat, h.lon], {
            icon: createDotIcon('#a34456', h.type.toUpperCase())
        }).bindPopup(`<strong>Active roadblock / hazard</strong><br/>Type: ${h.type}`).addTo(map);
    });

    // 4. Routes (color-coded)
    const hasHazards = (world.hazards || []).length > 0;
    (world.routes || []).forEach((route, idx) => {
        let coords;
        if (Array.isArray(route.geometry)) {
            coords = route.geometry;
        } else if (route.geometry && route.geometry.coordinates) {
            coords = route.geometry.coordinates.map(c => [c[1], c[0]]);
        }
        if (coords && coords.length > 0) {
            const color = mode === 'dynamic'
                ? (hasHazards ? '#3a8f6b' : '#5b8fb0') // pine for QPSO detour, steel for normal
                : (hasHazards ? '#a34456' : '#55565b'); // wine for static blocked, gray for normal
            const weight = mode === 'dynamic' ? 4.5 : 3.5;
            const opacity = mode === 'dynamic' ? 0.92 : 0.7;

            const polyline = L.polyline(coords, { color, weight, opacity, lineJoin: 'round', lineCap: 'round' }).addTo(map);

            // Snap the same ordered waypoints onto real streets client-side,
            // then swap the drawn line in once resolved (falls back silently
            // to the straight line above if the public router is unreachable).
            if (coords.length > 1) {
                const snapKey = coords.map((c) => c.join(',')).join(';');
                polyline._snapKey = snapKey;
                snapRouteToRoads(coords).then((snapped) => {
                    if (snapped && map.hasLayer(polyline) && polyline._snapKey === snapKey) {
                        polyline.setLatLngs(snapped);
                    }
                });
            }
        }
    });

    // 5. Animated rider positions
    if (positions) {
        Object.entries(positions).forEach(([vid, pos]) => {
            if (pos && pos.lat && pos.lon) {
                const isBlocked = mode === 'static' && (world.hazards || []).length > 0 && pos.progress > 0.3 && !pos.completed;
                const label = isBlocked ? `Rider ${vid} · blocked` : `Rider ${vid}`;
                const color = isBlocked ? '#a34456' : '#d8d7d3';

                L.marker([pos.lat, pos.lon], {
                    icon: createVehicleIcon(color, label, isBlocked)
                }).bindPopup(`<strong>Delivery partner #${vid}</strong><br/>Progress: ${(pos.progress * 100).toFixed(0)}%`).addTo(map);
            }
        });
    }
};

export const SplitScreenMap = ({
    staticWorld,
    dynamicWorld,
    positions,
    onMapClick,
    pendingPickup,
    activeTool
}) => {
    const staticMapRef = useRef(null);
    const dynamicMapRef = useRef(null);
    const staticContainer = useRef(null);
    const dynamicContainer = useRef(null);
    const onMapClickRef = useRef(onMapClick);

    useEffect(() => {
        onMapClickRef.current = onMapClick;
    }, [onMapClick]);

    useEffect(() => {
        if (!staticMapRef.current && staticContainer.current) {
            staticMapRef.current = L.map(staticContainer.current).setView([17.445, 78.37], 13);
            L.tileLayer(TILE_URL, { attribution: TILE_ATTR, className: 'map-tiles-dark' }).addTo(staticMapRef.current);
            staticMapRef.current.on('click', (e) => onMapClickRef.current && onMapClickRef.current(e.latlng));
        }
        if (!dynamicMapRef.current && dynamicContainer.current) {
            dynamicMapRef.current = L.map(dynamicContainer.current).setView([17.445, 78.37], 13);
            L.tileLayer(TILE_URL, { attribution: TILE_ATTR, className: 'map-tiles-dark' }).addTo(dynamicMapRef.current);
            dynamicMapRef.current.on('click', (e) => onMapClickRef.current && onMapClickRef.current(e.latlng));
        }

        if (staticMapRef.current && dynamicMapRef.current) {
            syncMaps(staticMapRef.current, dynamicMapRef.current);
        }

        return () => {
            if (staticMapRef.current) { staticMapRef.current.remove(); staticMapRef.current = null; }
            if (dynamicMapRef.current) { dynamicMapRef.current.remove(); dynamicMapRef.current = null; }
        };
    }, []);

    useEffect(() => {
        if (staticWorld && staticMapRef.current) {
            renderWorld(staticMapRef.current, staticWorld, positions?.static, 'static');
            if (pendingPickup) {
                L.marker([pendingPickup.lat, pendingPickup.lng], {
                    icon: createDotIcon('#c08a3e', 'Pickup set — click dropoff'),
                    zIndexOffset: 2000
                }).addTo(staticMapRef.current);
            }
        }
    }, [staticWorld, positions?.static, pendingPickup]);

    useEffect(() => {
        if (dynamicWorld && dynamicMapRef.current) {
            renderWorld(dynamicMapRef.current, dynamicWorld, positions?.dynamic, 'dynamic');
            if (pendingPickup) {
                L.marker([pendingPickup.lat, pendingPickup.lng], {
                    icon: createDotIcon('#c08a3e', 'Pickup set — click dropoff'),
                    zIndexOffset: 2000
                }).addTo(dynamicMapRef.current);
            }
        }
    }, [dynamicWorld, positions?.dynamic, pendingPickup]);

    return (
        <div style={{ display: 'flex', height: '520px', width: '100%', gap: '12px' }}>
            {/* Left Screen: Static */}
            <div style={{ flex: 1, position: 'relative', border: '1px solid var(--border-default)', borderRadius: '6px', overflow: 'hidden' }}>
                <div style={{
                    position: 'absolute', zIndex: 1000, top: '10px', left: '10px',
                    background: 'rgba(20, 21, 25, 0.92)', padding: '6px 12px', borderRadius: '5px',
                    border: '1px solid var(--border-default)', borderLeft: '2px solid var(--wine-bright)'
                }}>
                    <div style={{ fontWeight: 600, fontSize: '12.5px', color: 'var(--text-primary)' }}>
                        Static baseline routing
                    </div>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-tertiary)' }}>
                        Fixed sequence — delayed and stuck on roadblock
                    </div>
                </div>
                <div ref={staticContainer} style={{ width: '100%', height: '100%' }} />
            </div>

            {/* Right Screen: Dynamic QPSO */}
            <div style={{ flex: 1, position: 'relative', border: '1px solid var(--border-default)', borderRadius: '6px', overflow: 'hidden' }}>
                <div style={{
                    position: 'absolute', zIndex: 1000, top: '10px', left: '10px',
                    background: 'rgba(20, 21, 25, 0.92)', padding: '6px 12px', borderRadius: '5px',
                    border: '1px solid var(--border-default)', borderLeft: '2px solid var(--pine-bright)'
                }}>
                    <div style={{ fontWeight: 600, fontSize: '12.5px', color: 'var(--text-primary)' }}>
                        Dynamic QPSO engine (self-healing)
                    </div>
                    <div style={{ fontSize: '10.5px', color: 'var(--text-tertiary)' }}>
                        Real-time re-routing — instantly detours around hazards
                    </div>
                </div>
                <div ref={dynamicContainer} style={{ width: '100%', height: '100%' }} />
            </div>
        </div>
    );
};
