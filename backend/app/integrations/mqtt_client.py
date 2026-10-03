"""
Scalable IoT ingestion layer (Section 7): Eclipse Mosquitto MQTT broker
client using paho-mqtt, processing bi-directional telemetry from simulated
vehicle edge nodes and driver mobile apps, feeding live vehicle
position/status back into the optimizer and UI (via the FastAPI WebSocket
bridge in app/main.py).

Topics:
  fleet/{vehicle_id}/telemetry   (vehicle -> backend: lat, lon, speed, soc)
  fleet/{vehicle_id}/status      (vehicle -> backend: enroute/onscene/available)
  fleet/{vehicle_id}/command     (backend -> vehicle: new route push)

Run standalone against a local Mosquitto broker started by docker-compose:
`python -m app.integrations.mqtt_client`
"""
from __future__ import annotations
import json
import os
import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

TELEMETRY_TOPIC = "fleet/+/telemetry"
STATUS_TOPIC = "fleet/+/status"


class FleetMQTTBridge:
    def __init__(self, on_telemetry: Callable[[int, dict], None] | None = None,
                 on_status: Callable[[int, dict], None] | None = None,
                 host: str = MQTT_HOST, port: int = MQTT_PORT):
        self.host, self.port = host, port
        self.on_telemetry_cb = on_telemetry
        self.on_status_cb = on_status
        self.client = mqtt.Client(client_id="ambulance-router-backend", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe(TELEMETRY_TOPIC)
        client.subscribe(STATUS_TOPIC)

    def _on_message(self, client, userdata, msg):
        try:
            vehicle_id = int(msg.topic.split("/")[1])
            payload = json.loads(msg.payload.decode())
        except Exception:
            return
        if msg.topic.endswith("/telemetry") and self.on_telemetry_cb:
            self.on_telemetry_cb(vehicle_id, payload)
        elif msg.topic.endswith("/status") and self.on_status_cb:
            self.on_status_cb(vehicle_id, payload)

    def connect_and_loop_forever(self):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_forever()

    def connect_background(self):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def push_command(self, vehicle_id: int, route: list[int]):
        self.client.publish(f"fleet/{vehicle_id}/command", json.dumps({"route": route, "ts": time.time()}))


def simulate_vehicle_edge_node(vehicle_id: int, start_lat: float, start_lon: float,
                                host: str = MQTT_HOST, port: int = MQTT_PORT, n_ticks: int = 60):
    """Simulated vehicle edge node / driver mobile app publisher, standing
    in for real hardware telemetry so the MQTT loop is exercisable without
    physical ambulances -- publishes real MQTT messages to a real broker."""
    client = mqtt.Client(client_id=f"vehicle-sim-{vehicle_id}")
    client.connect(host, port, keepalive=30)
    lat, lon, soc = start_lat, start_lon, 1.0
    for _ in range(n_ticks):
        lat += 0.0005
        lon += 0.0003
        soc = max(0.0, soc - 0.004)
        client.publish(f"fleet/{vehicle_id}/telemetry",
                        json.dumps({"lat": lat, "lon": lon, "speed_kmh": 38.0, "soc": soc, "ts": time.time()}))
        time.sleep(1)
    client.disconnect()


if __name__ == "__main__":
    bridge = FleetMQTTBridge(on_telemetry=lambda vid, p: print("telemetry", vid, p),
                              on_status=lambda vid, p: print("status", vid, p))
    bridge.connect_and_loop_forever()
