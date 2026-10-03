"""
Local mock Beckn Protocol registry/BAP counterpart (Section 7), used so the
ONDC LSP client code below can be exercised end-to-end without a live
production ONDC registry account. Speaks the same `search`/`on_search`,
`init`/`on_init`, `confirm`/`on_confirm`, `status`/`on_status` message
shapes as the real network, so pointing `BecknClient` at a production
Beckn gateway URL instead of this mock is a config change, not a rewrite.

Run standalone: `uvicorn app.integrations.beckn_mock_server:app --port 6000`
"""
from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
import uuid
import time

app = FastAPI(title="Beckn Mock Registry (dev)")

_orders: dict[str, dict] = {}


class BecknContext(BaseModel):
    domain: str = "logistics"
    action: str
    transaction_id: str
    message_id: str = ""
    timestamp: str = ""


class BecknMessage(BaseModel):
    context: BecknContext
    message: dict


@app.post("/search")
def search(req: BecknMessage):
    intent = req.message.get("intent", {})
    catalog = {
        "providers": [{
            "id": "provider.ambulance-fleet.local",
            "items": [{
                "id": "item.ambulance-dispatch",
                "price": {"currency": "INR", "value": "0"},
                "descriptor": {"name": "QPSO-routed ambulance dispatch"},
                "fulfillment_id": str(uuid.uuid4()),
            }],
        }]
    }
    return {"context": {**req.context.dict(), "action": "on_search"}, "message": {"catalog": catalog}}


@app.post("/init")
def init(req: BecknMessage):
    order_id = str(uuid.uuid4())
    _orders[order_id] = {"status": "INITIALIZED", "message": req.message, "ts": time.time()}
    return {"context": {**req.context.dict(), "action": "on_init"},
            "message": {"order": {"id": order_id, "state": "INITIALIZED"}}}


@app.post("/confirm")
def confirm(req: BecknMessage):
    order_id = req.message.get("order", {}).get("id")
    if order_id in _orders:
        _orders[order_id]["status"] = "CONFIRMED"
    return {"context": {**req.context.dict(), "action": "on_confirm"},
            "message": {"order": {"id": order_id, "state": "CONFIRMED"}}}


@app.post("/status")
def status(req: BecknMessage):
    order_id = req.message.get("order_id")
    order = _orders.get(order_id, {"status": "UNKNOWN"})
    return {"context": {**req.context.dict(), "action": "on_status"},
            "message": {"order": {"id": order_id, "state": order["status"]}}}
