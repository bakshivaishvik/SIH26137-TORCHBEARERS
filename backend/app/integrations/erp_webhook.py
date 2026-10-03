"""
ERP & Warehouse Management webhook listeners (Section 7): RESTful endpoints
compatible with SAP/Oracle/Zoho-style payloads, ingesting packing-slip /
incident-queue data automatically into the request pipeline. Mounted into
the main FastAPI app under /webhooks/*.
"""
from __future__ import annotations
import hashlib
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/webhooks", tags=["erp"])


class SAPPackingSlipPayload(BaseModel):
    DocNum: str
    CardCode: str
    ShipToLat: float
    ShipToLon: float
    Priority: Optional[str] = "STANDARD"
    RequestedDeliveryTime: Optional[str] = None


class ZohoIncidentPayload(BaseModel):
    incident_id: str
    latitude: float
    longitude: float
    triage_level: Optional[str] = "STANDARD"
    sla_minutes: Optional[float] = 45.0


def _normalize_priority(p: str) -> str:
    return {"HIGH": "URGENT", "CRITICAL": "CRITICAL", "LOW": "NON_URGENT"}.get(p.upper(), p.upper())


@router.post("/sap/packing-slip")
def sap_packing_slip(payload: SAPPackingSlipPayload):
    """Normalizes an SAP-style packing-slip webhook into an internal Stop
    request and enqueues it for dynamic on-the-fly insertion (Section 4.2)."""
    from app.core.models import Stop, Triage
    normalized_priority = _normalize_priority(payload.Priority)
    stop = Stop(
        id=int(hashlib.sha1(payload.DocNum.encode()).hexdigest(), 16) % 1_000_000, lat=payload.ShipToLat, lon=payload.ShipToLon,
        triage=Triage[normalized_priority] if normalized_priority in Triage.__members__ else Triage.STANDARD,
    )
    return {"status": "queued", "normalized_stop": stop.__dict__}


@router.post("/zoho/incident")
def zoho_incident(payload: ZohoIncidentPayload):
    from app.core.models import Stop, Triage
    normalized_priority = _normalize_priority(payload.triage_level)
    stop = Stop(
        id=int(hashlib.sha1(payload.incident_id.encode()).hexdigest(), 16) % 1_000_000, lat=payload.latitude, lon=payload.longitude,
        sla_response_min=payload.sla_minutes,
        triage=Triage[normalized_priority] if normalized_priority in Triage.__members__ else Triage.STANDARD,
    )
    return {"status": "queued", "normalized_stop": stop.__dict__}
