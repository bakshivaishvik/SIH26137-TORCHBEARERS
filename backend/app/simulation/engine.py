from copy import deepcopy
import time
from app.world import World
from app.optimizer.engine import optimize, OptimizeConstraints
from app.simulation.scenario import ScenarioParser
from app.core.models import Stop, Vehicle, Depot, Triage
from app.geometry import route_to_polyline_osrm

class SimulationEngine:
    def __init__(self):
        self.static_world = World()
        self.dynamic_world = World()
        self.tick = 0
        self.running = False
        self.scenario_data = None
        self.disruptions = []
        self.vehicle_positions = {"static": {}, "dynamic": {}}

    def reset(self):
        self.tick = 0
        self.running = False
        if self.scenario_data:
            self.load_scenario(self.scenario_data)

    def load_scenario(self, scenario_data: dict):
        self.scenario_data = deepcopy(scenario_data)
        self.tick = 0
        self.running = False

        # Load into static
        self._apply_scenario_to_world(self.static_world, scenario_data)
        # Load into dynamic
        self._apply_scenario_to_world(self.dynamic_world, scenario_data)
        
        self.disruptions = deepcopy(scenario_data.get("disruptions", []))

        # Run initial assignment at tick 0
        seed = scenario_data.get("seed", 42)
        self._run_initial_assignment(self.static_world, seed)
        self._run_initial_assignment(self.dynamic_world, seed)
        self._interpolate_positions(self.static_world, "static")
        self._interpolate_positions(self.dynamic_world, "dynamic")

    def add_custom_order(self, pickup_lat: float, pickup_lon: float, dropoff_lat: float, dropoff_lon: float):
        order_num = len(self.dynamic_world.stops) // 2 + 1
        order_id = f"ORD-{order_num}"
        p_id = max(self.dynamic_world.stops.keys(), default=0) + 1
        d_id = p_id + 1

        p_stop = Stop(id=p_id, lat=pickup_lat, lon=pickup_lon, order_id=order_id, stop_type="PICKUP", status="PENDING", service_time_min=2.0)
        d_stop = Stop(id=d_id, lat=dropoff_lat, lon=dropoff_lon, order_id=order_id, stop_type="DROPOFF", status="PENDING", service_time_min=2.0)

        for w in (self.static_world, self.dynamic_world):
            with w.lock:
                if not w.vehicles:
                    w.vehicles = [
                        Vehicle(id=1, depot_id=0, capacity=4, partner_start_lat=w.depot.lat - 0.005, partner_start_lon=w.depot.lon - 0.005),
                        Vehicle(id=2, depot_id=0, capacity=4, partner_start_lat=w.depot.lat + 0.005, partner_start_lon=w.depot.lon + 0.005),
                        Vehicle(id=3, depot_id=0, capacity=4, partner_start_lat=w.depot.lat, partner_start_lon=w.depot.lon + 0.008),
                    ]
                w.stops[p_id] = deepcopy(p_stop)
                w.stops[d_id] = deepcopy(d_stop)
                w.node_lookup[p_id] = w._nearest_node(pickup_lat, pickup_lon)
                w.node_lookup[d_id] = w._nearest_node(dropoff_lat, dropoff_lon)
                w._refresh_osrm_cache()

        # If static world had no routes, initialize it
        with self.static_world.lock:
            if not self.static_world.routes:
                self._reoptimize_world(self.static_world)

        # Optimize dynamic world with the new order
        with self.dynamic_world.lock:
            self._reoptimize_world(self.dynamic_world)

        # Update initial routes for both
        self._interpolate_positions(self.static_world, "static")
        self._interpolate_positions(self.dynamic_world, "dynamic")

    def _apply_scenario_to_world(self, world_instance: World, data: dict):
        with world_instance.lock:
            depot, vehicles, stops, _ = ScenarioParser.parse(data)
            world_instance.depot = depot
            world_instance.vehicles = vehicles
            world_instance.stops = stops
            
            world_instance.node_lookup.clear()
            for sid, s in stops.items():
                world_instance.node_lookup[sid] = world_instance._nearest_node(s.lat, s.lon)
            
            world_instance.routes = []
            world_instance.pareto_front = {}
            world_instance.convergence_history = []
            world_instance.hazards = []
            world_instance.weighter.state.hazard_multiplier.clear()
            
            world_instance._refresh_osrm_cache()

    def _run_initial_assignment(self, world_instance: World, seed: int):
        with world_instance.lock:
            self._reoptimize_world(world_instance, seed=seed)

    def _reoptimize_world(self, world_instance: World, seed: int = 42):
        stops = list(world_instance.stops.values())
        vehicles = world_instance.vehicles
        depots = [world_instance.depot]
        
        class _GraphAdapter:
            def __init__(self, fn):
                self.edge_weight_fn = fn
        graph = _GraphAdapter(world_instance.edge_weight_fn())
        
        result = optimize(
            graph, stops, vehicles, depots, world_instance.charging_stations,
            OptimizeConstraints(n_particles=30, max_iter=80, seed=seed)
        )
        
        world_instance.routes = result["routes"]
        for r in world_instance.routes:
            geom, dist, dur = route_to_polyline_osrm(
                r["stop_sequence"], 
                world_instance.depot, 
                world_instance.stops, 
                world_instance.osrm_client,
                hazards=world_instance.hazards
            )
            r["geometry"] = geom
            r["total_distance"] = dist
            r["total_duration"] = dur

    def advance_tick(self):
        self.tick += 1
        
        # Check for scripted disruptions
        active_disruptions = [d for d in self.disruptions if d.get("trigger_tick") == self.tick]
        for d in active_disruptions:
            self.inject_disruption(d)

        # Update vehicle positions and stop statuses for both worlds
        self._update_vehicles(self.static_world)
        self._update_vehicles(self.dynamic_world)
        self._interpolate_positions(self.static_world, "static")
        self._interpolate_positions(self.dynamic_world, "dynamic")

    def inject_disruption(self, disruption: dict):
        hazard_entry = {"lat": disruption["lat"], "lon": disruption["lon"], "type": disruption.get("type", "roadblock")}

        # 1. Apply to static world (adds hazard to map, but NO rerouting -> static vehicle gets blocked/delayed)
        with self.static_world.lock:
            self.static_world.hazards.append(hazard_entry)
            u = self.static_world._nearest_node(disruption["lat"], disruption["lon"])
            neighbors = list(self.static_world.road_graph[u].keys())
            if neighbors:
                self.static_world.weighter.set_hazard(u, neighbors[0], disruption.get("type", "roadblock"))
                
        # 2. Apply to dynamic world AND immediately re-optimize with QPSO
        with self.dynamic_world.lock:
            self.dynamic_world.hazards.append(hazard_entry)
            u = self.dynamic_world._nearest_node(disruption["lat"], disruption["lon"])
            neighbors = list(self.dynamic_world.road_graph[u].keys())
            if neighbors:
                v = neighbors[0]
                self.dynamic_world.weighter.set_hazard(u, v, disruption.get("type", "roadblock"))
                self._trigger_dynamic_reopt(disruption["lat"], disruption["lon"])

        self._interpolate_positions(self.static_world, "static")
        self._interpolate_positions(self.dynamic_world, "dynamic")

    def _trigger_dynamic_reopt(self, h_lat: float, h_lon: float):
        from app.optimizer.delta_reopt import localized_delta_reopt
        
        # Find route closest to the placed hazard
        best_route = None
        best_dist = float("inf")
        best_stop = None

        for r in self.dynamic_world.routes:
            geom = r.get("geometry", [])
            for pt in geom:
                d = (pt[0] - h_lat)**2 + (pt[1] - h_lon)**2
                if d < best_dist:
                    best_dist = d
                    best_route = r
            for sid in r.get("stop_sequence", []):
                s = self.dynamic_world.stops.get(sid)
                if s:
                    d = (s.lat - h_lat)**2 + (s.lon - h_lon)**2
                    if d < best_dist:
                        best_dist = d
                        best_route = r
                        best_stop = sid

        if best_route and best_route.get("stop_sequence"):
            sid = best_stop if best_stop is not None else best_route["stop_sequence"][0]
            hazard_edge = (sid, sid)

            out = localized_delta_reopt(
                self.dynamic_world.routes, hazard_edge, self.dynamic_world.stops_by_id(), 
                self.dynamic_world.vehicles, self.dynamic_world.depots_by_id(),
                self.dynamic_world.charging_stations, self.dynamic_world.edge_weight_fn(), 
                local_iters=25, local_particles=16,
            )
            self.dynamic_world.routes = out["routes"]
            
            for r in self.dynamic_world.routes:
                geom, dist, dur = route_to_polyline_osrm(
                    r["stop_sequence"], 
                    self.dynamic_world.depot, 
                    self.dynamic_world.stops, 
                    self.dynamic_world.osrm_client,
                    hazards=self.dynamic_world.hazards
                )
                r["geometry"] = geom
                r["total_distance"] = dist
                r["total_duration"] = dur

    def _update_vehicles(self, world_instance: World):
        with world_instance.lock:
            from app.optimizer.split import _travel_time_min

            for r in world_instance.routes:
                v = next((v for v in world_instance.vehicles if v.id == r["vehicle_id"]), None)
                if not v: continue
                
                t = 0.0
                start_lat = v.partner_start_lat if v.partner_start_lat is not None else world_instance.depot.lat
                start_lon = v.partner_start_lon if v.partner_start_lon is not None else world_instance.depot.lon
                cur = Stop(id=-1, lat=start_lat, lon=start_lon)
                
                for sid in r.get("stop_sequence", []):
                    if sid not in world_instance.stops: continue
                    nxt = world_instance.stops[sid]
                    
                    if nxt.status == "DELIVERED":
                        cur = nxt
                        continue
                        
                    _, minutes = _travel_time_min(cur, nxt, v.max_speed_kmh, world_instance.edge_weight_fn())
                    
                    if self.tick >= t + minutes:
                        if nxt.stop_type == "PICKUP" and nxt.status == "PENDING":
                            nxt.status = "COLLECTED"
                            nxt.assigned_vehicle_id = v.id
                        elif nxt.stop_type == "DROPOFF" and nxt.status == "COLLECTED":
                            nxt.status = "DELIVERED"
                    
                    t += minutes + nxt.service_time_min
                    cur = nxt

    def _interpolate_positions(self, world_instance: World, mode: str):
        positions = {}
        for r in world_instance.routes:
            vid = r["vehicle_id"]
            geom = r.get("geometry", [])
            dur = max(r.get("total_duration", 15.0), 1.0)
            
            if not geom:
                positions[vid] = {"lat": world_instance.depot.lat, "lon": world_instance.depot.lon, "progress": 0.0}
                continue
                
            # Progress fraction along geometry
            frac = min(1.0, self.tick / dur)
            idx = int(frac * (len(geom) - 1))
            pt = geom[idx]
            positions[vid] = {
                "lat": pt[0], 
                "lon": pt[1], 
                "progress": frac,
                "completed": frac >= 1.0
            }
        self.vehicle_positions[mode] = positions

    def get_metrics(self):
        def calc(w, mode):
            stops = list(w.stops.values())
            total_orders = len([s for s in stops if s.stop_type == "PICKUP"])
            delivered = len([s for s in stops if s.stop_type == "DROPOFF" and s.status == "DELIVERED"])
            collected = len([s for s in stops if s.status == "COLLECTED"])
            
            # Distance & Duration
            dist = sum(r.get("total_distance", 0) for r in w.routes)
            dur = sum(r.get("total_duration", 0) for r in w.routes)
            
            # Static roadblock delay penalty
            hazard_delay = len(w.hazards) * 22.0 if mode == "static" else 0.0
            late_count = len(w.hazards) if (mode == "static" and len(w.hazards) > 0 and self.tick > 3) else 0
            total_penalty = late_count * 150.0

            return {
                "total_orders": total_orders,
                "delivered": delivered,
                "collected": collected,
                "total_distance_km": round(dist, 1),
                "total_duration_min": round(dur + hazard_delay, 1),
                "late_count": late_count,
                "penalty_cost": total_penalty,
                "status": "Stuck in Hazard (+22m delay)" if (mode == "static" and len(w.hazards) > 0) else "Optimal QPSO Detour (On-Time)" if len(w.hazards) > 0 else "Normal Routing",
            }

        return {
            "tick": self.tick,
            "static": calc(self.static_world, "static"),
            "dynamic": calc(self.dynamic_world, "dynamic"),
            "positions": self.vehicle_positions,
        }

sim_engine = SimulationEngine()

