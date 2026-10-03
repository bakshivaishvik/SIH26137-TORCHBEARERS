"""
Road-following route geometry helper.

Turns a route's stop sequence into a real polyline that follows the
road-graph edges (via Dijkstra between consecutive stops' nearest nodes)
instead of a straight depot->stop->depot line, so the frontend map renders
routes along the street network. When a live OSRM/GraphHopper container is
running (app.graph.osrm_client.OSRMClient), prefer its /route geometry
instead -- this function is the offline-graph fallback used by the
in-sandbox synthetic city grid and by any NetworkX-loaded OSM graph.
"""
from app.core.models import Stop, Depot
from app.graph.osrm_client import OSRMClient

def _point_near_segment(p_lat: float, p_lon: float, a_lat: float, a_lon: float, b_lat: float, b_lon: float, threshold_km: float = 0.25) -> bool:
    # Check if point p is close to segment a-b
    mid_lat, mid_lon = (a_lat + b_lat) / 2.0, (a_lon + b_lon) / 2.0
    d_mid = ((mid_lat - p_lat) ** 2 + (mid_lon - p_lon) ** 2) ** 0.5 * 111.0
    return d_mid < threshold_km

def route_to_polyline_osrm(
    stop_sequence: list[int], 
    depot: Depot, 
    stops_by_id: dict, 
    osrm_client: OSRMClient,
    hazards: list[dict] | None = None
) -> tuple[list[list[float]], float, float]:
    points = [Stop(id=depot.id, lat=depot.lat, lon=depot.lon, demand=0, tw_start_min=0, tw_hard_end_min=0, tw_soft_end_min=0, sla_response_min=0, triage=1)]
    for sid in stop_sequence:
        if sid in stops_by_id:
            points.append(stops_by_id[sid])
    points.append(Stop(id=depot.id, lat=depot.lat, lon=depot.lon, demand=0, tw_start_min=0, tw_hard_end_min=0, tw_soft_end_min=0, sla_response_min=0, triage=1))

    coords: list[list[float]] = []
    total_dist_km = 0.0
    total_dur_min = 0.0
    active_hazards = hazards or []
    
    for a, b in zip(points[:-1], points[1:]):
        # Check if any active hazard intersects this leg
        detour_waypoint = None
        for h in active_hazards:
            h_lat, h_lon = h.get("lat", 0.0), h.get("lon", 0.0)
            if _point_near_segment(h_lat, h_lon, a.lat, a.lon, b.lat, b.lon, threshold_km=0.8):
                # Compute a detour point perpendicular to the direct vector
                d_lat = b.lat - a.lat
                d_lon = b.lon - a.lon
                length = (d_lat**2 + d_lon**2)**0.5 or 1e-4
                # Normal vector offset ~400m
                perp_lat = -d_lon / length * 0.004
                perp_lon = d_lat / length * 0.004
                detour_waypoint = Stop(id=-999, lat=h_lat + perp_lat, lon=h_lon + perp_lon)
                break

        if detour_waypoint is not None:
            # Route through detour waypoint: a -> detour -> b
            res1 = osrm_client.route(a, detour_waypoint)
            res2 = osrm_client.route(detour_waypoint, b)
            total_dist_km += res1.get("distance_km", 0.0) + res2.get("distance_km", 0.0)
            total_dur_min += res1.get("duration_min", 0.0) + res2.get("duration_min", 0.0)
            
            g1 = res1.get("geometry", {})
            if g1 and "coordinates" in g1:
                for lon, lat in g1["coordinates"]:
                    coords.append([lat, lon])
            g2 = res2.get("geometry", {})
            if g2 and "coordinates" in g2:
                for lon, lat in g2["coordinates"]:
                    coords.append([lat, lon])
        else:
            res = osrm_client.route(a, b)
            total_dist_km += res.get("distance_km", 0.0)
            total_dur_min += res.get("duration_min", 0.0)
            
            geom = res.get("geometry", {})
            if geom and "coordinates" in geom:
                for lon, lat in geom["coordinates"]:
                    coords.append([lat, lon])
                
    return coords, total_dist_km, total_dur_min
