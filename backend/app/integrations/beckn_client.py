"""
ONDC / Beckn Protocol LSP (Logistics Service Provider) client (Section 7).

Implements the real `search` -> `init` -> `confirm` -> `status` call
sequence so this system can act as an automated LSP bidding on dispatch
requests by marginal insertion cost (the cost delta `optimizer.engine`
reports for inserting a new incident into the current fleet, Section 4.2).

Points at BECKN_BASE_URL, which defaults to the local mock server in
beckn_mock_server.py; swapping to a production ONDC gateway is a one-line
config change (set BECKN_BASE_URL to the registry's URL + credentials),
not a rewrite -- the message shapes are identical to the real protocol.
"""
from __future__ import annotations
import os
import uuid
import time
import httpx

BECKN_BASE_URL = os.environ.get("BECKN_BASE_URL", "http://localhost:6000")


class BecknClient:
    def __init__(self, base_url: str = BECKN_BASE_URL, domain: str = "logistics", timeout_sec: float = 5.0):
        self.base_url = base_url
        self.domain = domain
        self.timeout_sec = timeout_sec

    def _context(self, action: str, transaction_id: str) -> dict:
        return {
            "domain": self.domain, "action": action, "transaction_id": transaction_id,
            "message_id": str(uuid.uuid4()), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def search(self, pickup: dict, drop: dict, transaction_id: str | None = None) -> dict:
        tid = transaction_id or str(uuid.uuid4())
        payload = {"context": self._context("search", tid),
                   "message": {"intent": {"fulfillment": {"start": {"location": pickup},
                                                            "end": {"location": drop}}}}}
        r = httpx.post(f"{self.base_url}/search", json=payload, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def init(self, transaction_id: str, order_payload: dict) -> dict:
        payload = {"context": self._context("init", transaction_id), "message": order_payload}
        r = httpx.post(f"{self.base_url}/init", json=payload, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def confirm(self, transaction_id: str, order_id: str) -> dict:
        payload = {"context": self._context("confirm", transaction_id),
                   "message": {"order": {"id": order_id}}}
        r = httpx.post(f"{self.base_url}/confirm", json=payload, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def status(self, transaction_id: str, order_id: str) -> dict:
        payload = {"context": self._context("status", transaction_id), "message": {"order_id": order_id}}
        r = httpx.post(f"{self.base_url}/status", json=payload, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()

    def bid_by_marginal_insertion_cost(self, pickup: dict, drop: dict, marginal_cost: float,
                                        max_acceptable_cost: float) -> dict:
        """Automated LSP bidding logic: only proceed through init/confirm if
        the optimizer's marginal insertion cost (Section 4.2) is within the
        acceptable ceiling for this request class."""
        tid = str(uuid.uuid4())
        search_result = self.search(pickup, drop, tid)
        if marginal_cost > max_acceptable_cost:
            return {"bid": "DECLINED", "reason": "marginal_cost_exceeds_ceiling",
                     "marginal_cost": marginal_cost, "search_result": search_result}
        init_result = self.init(tid, {"order": {"items": [{"id": "item.ambulance-dispatch"}]}})
        order_id = init_result["message"]["order"]["id"]
        confirm_result = self.confirm(tid, order_id)
        return {"bid": "ACCEPTED", "order_id": order_id, "marginal_cost": marginal_cost,
                 "confirm_result": confirm_result}
