"""Router status endpoint: connection state plus derived diagnosis and recommendations.

``GET /router/status`` merges the live connection state of the snapshot feed
(``connected``, ``source``, ``device_id``, ``last_snapshot_at``, ``sequence``,
``error``, ``server_time``) with a single :class:`RouterSnapshot` and its
derived diagnosis and recommendations. The connection-state fields are preserved
from the original lightweight status contract so existing clients keep working
unchanged. When the router is unavailable the snapshot is ``null`` and the
diagnosis/recommendation arrays are empty (HTTP 200). JSON only — no markdown.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

from app.services.router_diagnosis import RouterDiagnosisEngine
from app.services.router_recommendation import RouterRecommendationEngine
from app.services.router_snapshot import RouterSnapshot

router = APIRouter(tags=["router"])

_ALL_SECTIONS = ["system", "cpu", "memory", "storage", "network", "wifi"]

_diagnosis_engine = RouterDiagnosisEngine()
_recommendation_engine = RouterRecommendationEngine()


def _unavailable() -> dict:
    return {"snapshot": None, "diagnosis": [], "recommendations": []}


def _is_populated(snapshot: RouterSnapshot) -> bool:
    sections = (
        snapshot.system,
        snapshot.cpu,
        snapshot.memory,
        snapshot.storage,
        snapshot.network,
        snapshot.wifi,
    )
    return any(section not in (None, [], {}) for section in sections)


def _connection_state(request: Request) -> dict:
    """Return the preserved lightweight connection-state fields.

    Reads the latest :class:`DashboardUpdate` from the snapshot feed. These
    fields were part of the original ``/router/status`` contract and are kept
    for backward compatibility.
    """
    feed = getattr(request.app.state, "snapshot_service", None)
    update = feed.latest() if feed is not None else None
    return {
        "connected": update.connected if update else False,
        "source": update.source if update else getattr(feed, "source", "simulated"),
        "device_id": update.device_id if update else "",
        "last_snapshot_at": update.sent_at.isoformat() if update and update.sent_at else None,
        "sequence": update.sequence if update else 0,
        "error": update.error if update and update.error else None,
        "server_time": datetime.now().isoformat(),
    }


@router.get("/router/status")
def router_status(request: Request) -> dict:
    """Return connection state plus the derived router snapshot/status."""
    state = _connection_state(request)
    manager = getattr(request.app.state, "router_manager", None)
    router = getattr(manager, "default", None) if manager is not None else None
    if router is None:
        return {**state, **_unavailable()}
    try:
        snapshot = router.snapshot_service.build(router.executor, None, _ALL_SECTIONS)
    except Exception:  # noqa: BLE001 - surfaced as an empty status
        return {**state, **_unavailable()}
    if not _is_populated(snapshot):
        return {**state, **_unavailable()}
    diagnosis = _diagnosis_engine.diagnose(snapshot, router_id=router.router_id)
    recommendations = _recommendation_engine.generate(diagnosis)
    return {
        **state,
        "snapshot": snapshot.to_dict(),
        "diagnosis": [finding.to_dict() for finding in diagnosis.findings],
        "recommendations": [
            recommendation.to_dict() for recommendation in recommendations.recommendations
        ],
    }
