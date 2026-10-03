import json
import numpy as np
from app.core.models import Stop, Vehicle, Depot, Triage

class ScenarioParser:
    @staticmethod
    def generate_random_scenario(seed: int = 42, num_orders: int = 10, num_partners: int = 5):
        rng = np.random.default_rng(seed)
        # Hitech City bounding box roughly: 17.43 to 17.46, 78.35 to 78.39
        lat_min, lat_max = 17.43, 17.46
        lon_min, lon_max = 78.35, 78.39

        depot = Depot(id=0, lat=(lat_min+lat_max)/2, lon=(lon_min+lon_max)/2)

        vehicles = []
        for i in range(num_partners):
            v_lat = rng.uniform(lat_min, lat_max)
            v_lon = rng.uniform(lon_min, lon_max)
            vehicles.append({
                "id": i,
                "depot_id": 0,
                "capacity": 4, # allow multiple orders
                "partner_start_lat": v_lat,
                "partner_start_lon": v_lon
            })

        orders = []
        stop_id = 1
        for i in range(num_orders):
            p_lat = rng.uniform(lat_min, lat_max)
            p_lon = rng.uniform(lon_min, lon_max)
            d_lat = rng.uniform(lat_min, lat_max)
            d_lon = rng.uniform(lon_min, lon_max)
            order_id = f"ORD-{i+1}"
            
            # Pickup
            orders.append({
                "id": stop_id,
                "lat": p_lat,
                "lon": p_lon,
                "order_id": order_id,
                "stop_type": "PICKUP",
                "status": "PENDING",
                "service_time_min": 2.0
            })
            stop_id += 1
            
            # Dropoff
            orders.append({
                "id": stop_id,
                "lat": d_lat,
                "lon": d_lon,
                "order_id": order_id,
                "stop_type": "DROPOFF",
                "status": "PENDING",
                "service_time_min": 2.0
            })
            stop_id += 1

        return {
            "seed": seed,
            "depot": depot.__dict__,
            "vehicles": vehicles,
            "orders": orders,
            "disruptions": []
        }

    @staticmethod
    def parse(data: dict) -> tuple:
        depot_data = data["depot"]
        depot = Depot(**depot_data)
        
        vehicles = []
        for v in data["vehicles"]:
            vehicle = Vehicle(
                id=v["id"],
                depot_id=v["depot_id"],
                capacity=v.get("capacity", 4),
                is_single_patient=False
            )
            vehicle.partner_start_lat = v.get("partner_start_lat")
            vehicle.partner_start_lon = v.get("partner_start_lon")
            vehicles.append(vehicle)

        stops = {}
        for o in data["orders"]:
            stop = Stop(
                id=o["id"],
                lat=o["lat"],
                lon=o["lon"],
                triage=Triage.STANDARD,
                service_time_min=o.get("service_time_min", 2.0)
            )
            stop.order_id = o.get("order_id")
            stop.stop_type = o.get("stop_type")
            stop.status = o.get("status", "PENDING")
            stops[stop.id] = stop

        disruptions = data.get("disruptions", [])
        return depot, vehicles, stops, disruptions

