"""Internet speed test endpoints.

``POST /network/speed-test`` runs a dependency-free, read-only measurement of
the management host's internet link (latency/jitter via TCP timings; download
and upload via bounded public HTTPS transfers). The test never executes router
commands and never accepts user-controlled targets. Returns the measured JSON:

.. code-block:: json

    {
        "download_mbps": 245.4,
        "upload_mbps": 38.2,
        "ping_ms": 12.4,
        "jitter_ms": 2.8,
        "timestamp": "...",
        "duration_ms": 12345,
        "limitations": [],
        "complete": true
    }

``GET /network/speed-test`` returns the most recent result (``result: null``
before the first run) so the dashboard and a future Copilot feature can read it
without re-running the test.

Concurrency is bounded: only one test runs at a time (409 when busy) and a
cooldown applies between runs (429 when too soon). Read-only scope: any
authenticated reader may run a measurement.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import require_read
from app.services.speed_test import (
    SpeedTestBusy,
    SpeedTestCooldown,
    SpeedTestError,
    SpeedTestService,
)

router = APIRouter(tags=["network"])


def _service(request: Request) -> SpeedTestService:
    service: SpeedTestService | None = getattr(request.app.state, "speed_test_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Speed test service is not available.")
    return service


@router.post("/network/speed-test", dependencies=[Depends(require_read)])
async def run_speed_test(request: Request) -> dict:
    """Run an internet speed test (read-only; one at a time)."""
    service = _service(request)
    try:
        return await asyncio.to_thread(service.run)
    except SpeedTestBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SpeedTestCooldown as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except SpeedTestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/network/speed-test", dependencies=[Depends(require_read)])
def latest_speed_test(request: Request) -> dict:
    """Return the most recent speed test result (``result: null`` when none)."""
    return {"result": _service(request).latest()}
