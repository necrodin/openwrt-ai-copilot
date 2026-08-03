"""Router status endpoint: live snapshot plus derived diagnosis and recommendations.

``GET /router/status`` builds a single :class:`RouterSnapshot` from the
registered router, then derives diagnosis and recommendations from that one
snapshot. When the router is unavailable the endpoint returns ``null``/empty
arrays with HTTP 200. JSON only — no markdown.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.router_diagnosis import RouterDiagnosisEngine
from app.services.router_recommendation import RouterRecommendationEngine
from app.services.router_snapshot import RouterSnapshot

router = APIRouter(tags=["router"])

_ALL_SECTIONS = ["system", "cpu", "memory", "storage", "network"]

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


@router.get("/router/status")
def router_status(request: Request) -> dict:
    """Return the router snapshot and derived diagnosis/recommendations."""
    manager = getattr(request.app.state, "router_manager", None)
    router = getattr(manager, "default", None) if manager is not None else None
    if router is None:
        return _unavailable()
    try:
        snapshot = router.snapshot_service.build(router.executor, None, _ALL_SECTIONS)
    except Exception:  # noqa: BLE001 - surfaced as an empty status
        return _unavailable()
    if not _is_populated(snapshot):
        return _unavailable()
    diagnosis = _diagnosis_engine.diagnose(snapshot, router_id=router.router_id)
    recommendations = _recommendation_engine.generate(diagnosis)
    return {
        "snapshot": snapshot.to_dict(),
        "diagnosis": [finding.to_dict() for finding in diagnosis.findings],
        "recommendations": [
            recommendation.to_dict() for recommendation in recommendations.recommendations
        ],
    }
