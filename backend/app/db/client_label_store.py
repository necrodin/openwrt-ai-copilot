"""Persistent client device labels (SQLite via the shared database package).

Labels are keyed by MAC address only — never by IP — so a label survives a
device changing its address. Every write goes through :func:`normalize_mac` so
equivalent representations (``AA-BB-CC-11-22-33``, ``aa:bb:cc:11:22:33``,
``AABBCC112233``) map to the same canonical record.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.schema.client_label import ClientLabelRecord
from database.session import SessionLocal

SessionFactory = Callable[[], Session]

#: Exactly twelve hex octets, separators and case ignored.
_HEX_DIGITS = re.compile(r"[^0-9a-fA-F]")
_MAC_LENGTH = 12


def normalize_mac(mac: str) -> str | None:
    """Return the canonical ``aa:bb:cc:11:22:33`` form of ``mac``, or ``None``.

    Separators and case are normalized away and the twelve hex digits are
    regrouped into canonical colon-separated lowercase octets. An address with
    anything other than twelve hex digits (e.g. a hostname or a malformed MAC)
    is rejected so the store never keys on a non-MAC.
    """
    if not mac:
        return None
    digits = _HEX_DIGITS.sub("", mac)
    if len(digits) != _MAC_LENGTH:
        return None
    octets = [digits[i : i + 2] for i in range(0, _MAC_LENGTH, 2)]
    return ":".join(octets).lower()


class ClientLabelStore:
    """Store for operator-assigned per-MAC device labels."""

    def __init__(self, session_factory: SessionFactory = SessionLocal) -> None:
        """Bind the store to ``session_factory`` (defaults to the shared engine)."""
        self._session_factory = session_factory

    def list_all(self) -> list[ClientLabelRecord]:
        """Return every label, ordered by MAC address."""
        with self._session_factory() as session:
            stmt = select(ClientLabelRecord).order_by(ClientLabelRecord.mac_address.asc())
            return list(session.scalars(stmt).all())

    def get(self, mac: str) -> ClientLabelRecord | None:
        """Return the label record for a normalized MAC, if any."""
        normalized = normalize_mac(mac)
        if normalized is None:
            return None
        with self._session_factory() as session:
            stmt = select(ClientLabelRecord).where(
                ClientLabelRecord.mac_address == normalized
            )
            return session.scalars(stmt).first()

    def upsert(self, mac: str, label: str) -> ClientLabelRecord:
        """Create or update the label for a MAC, returning the record.

        A duplicate MAC updates the existing label (identity is the MAC), so
        re-labeling a device never creates a second row.
        """
        normalized = normalize_mac(mac)
        if normalized is None:
            raise ValueError(f"invalid MAC address: {mac!r}")
        with self._session_factory() as session:
            record = session.scalars(
                select(ClientLabelRecord).where(ClientLabelRecord.mac_address == normalized)
            ).first()
            if record is None:
                record = ClientLabelRecord(mac_address=normalized, label=label)
                session.add(record)
            else:
                record.label = label
            session.commit()
            session.refresh(record)
            return record

    def delete(self, mac: str) -> bool:
        """Delete the label for a MAC. Returns ``True`` when a row was removed."""
        normalized = normalize_mac(mac)
        if normalized is None:
            return False
        with self._session_factory() as session:
            record = session.scalars(
                select(ClientLabelRecord).where(ClientLabelRecord.mac_address == normalized)
            ).first()
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def to_public_dict(self, record: ClientLabelRecord) -> dict:
        """Return a JSON-safe view of a label record."""
        return {
            "mac_address": record.mac_address,
            "label": record.label,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }


store = ClientLabelStore()
