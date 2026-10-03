"""
Explainability & Auditability log (Section 8).

Every routing/rerouting decision is written as a structured, queryable
record: the triggering event, the before/after route, and the cost delta.
Backed by SQLite (zero external service needed) so it's queryable with
plain SQL as well as through the API the GenAI Copilot (Section 4.1) calls.
"""
from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "explainability_log.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,          -- 'new_request' | 'hazard' | 'forecast_update' | 'insertion'
    trigger_details TEXT NOT NULL,     -- JSON
    vehicle_id INTEGER,
    route_before TEXT,                 -- JSON list of stop ids
    route_after TEXT,                  -- JSON list of stop ids
    cost_before REAL,
    cost_after REAL,
    cost_delta REAL,
    narrative TEXT                     -- human-readable one-liner for the copilot
);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_decision(event_type: str, trigger_details: dict, vehicle_id: int | None,
                  route_before: list | None, route_after: list | None,
                  cost_before: float | None, cost_after: float | None,
                  narrative: str) -> int:
    delta = None
    if cost_before is not None and cost_after is not None:
        delta = cost_after - cost_before
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO decision_log (ts, event_type, trigger_details, vehicle_id, route_before, "
            "route_after, cost_before, cost_after, cost_delta, narrative) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.time(), event_type, json.dumps(trigger_details), vehicle_id,
             json.dumps(route_before) if route_before is not None else None,
             json.dumps(route_after) if route_after is not None else None,
             cost_before, cost_after, delta, narrative),
        )
        return cur.lastrowid


def query_decisions(vehicle_id: int | None = None, event_type: str | None = None,
                     since_ts: float | None = None, limit: int = 100) -> list[dict]:
    q = "SELECT * FROM decision_log WHERE 1=1"
    params = []
    if vehicle_id is not None:
        q += " AND vehicle_id = ?"
        params.append(vehicle_id)
    if event_type is not None:
        q += " AND event_type = ?"
        params.append(event_type)
    if since_ts is not None:
        q += " AND ts >= ?"
        params.append(since_ts)
    q += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for f in ("trigger_details", "route_before", "route_after"):
                if d.get(f):
                    d[f] = json.loads(d[f])
            out.append(d)
        return out
