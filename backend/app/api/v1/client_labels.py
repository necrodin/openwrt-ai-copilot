"""Client device-label endpoints.

Operator-assigned, persistent human-readable labels keyed by MAC address:

- ``GET    /clients/labels``     — list every label (any authenticated reader).
- ``PUT    /clients/labels/{mac}`` — create or update the label for a MAC.
- ``DELETE /clients/labels/{mac}`` — remove the label for a MAC.

Labels are application metadata only: they are stored in the local database,
never written into OpenWrt, and never change DHCP/ARP/WiFi configuration.
Writes require the admin/write scope (``devices.write``); reads follow the
existing authenticated read scope. MACs are normalized to the canonical
``aa:bb:cc:11:22:33`` form on every write, so equivalent representations map to
the same label.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth import AuthPrincipal, require_read, require_write
from app.db.client_label_store import ClientLabelStore, normalize_mac
from app.db.client_label_store import store as default_store

router = APIRouter(tags=["clients"])

#: Upper bound for a human-readable device label.
MAX_LABEL_LENGTH = 255


class LabelRequest(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)


def _store(request: Request) -> ClientLabelStore:
    """Resolve the label store (isolated stores can replace the default)."""
    return getattr(request.app.state, "client_label_store", None) or default_store


def _normalize_or_422(mac: str) -> str:
    normalized = normalize_mac(mac)
    if normalized is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid MAC address: {mac!r}",
        )
    return normalized


@router.get("/clients/labels")
def list_labels(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_read)],
) -> dict:
    """Return every stored label, ordered by MAC address."""
    store = _store(request)
    labels = [store.to_public_dict(record) for record in store.list_all()]
    return {"labels": labels}


@router.put("/clients/labels/{mac}")
def put_label(
    request: Request,
    mac: str,
    body: LabelRequest,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Create or update the label for a MAC (write/admin scope required)."""
    store = _store(request)
    normalized = _normalize_or_422(mac)
    label = body.label.strip()
    if not label:
        raise HTTPException(
            status_code=422,
            detail="Label must not be empty.",
        )
    record = store.upsert(normalized, label)
    return store.to_public_dict(record)


@router.delete("/clients/labels/{mac}")
def delete_label(
    request: Request,
    mac: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Remove the label for a MAC (write/admin scope required)."""
    store = _store(request)
    normalized = _normalize_or_422(mac)
    if not store.delete(normalized):
        raise HTTPException(
            status_code=404,
            detail=f"No label stored for MAC {normalized}.",
        )
    return {"deleted": True, "mac_address": normalized}
