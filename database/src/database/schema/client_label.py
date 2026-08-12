"""Persistent client device labels.

Operator-assigned, human-readable labels for a client device, keyed by its MAC
address (the only stable device identity that survives IP changes). The labels
are application-owned metadata: they are stored only here, never written into
OpenWrt, and never alter DHCP/ARP/WiFi configuration.

``mac_address`` is always stored in the canonical normalized form
(``aa:bb:cc:11:22:33``, lowercase, colon-separated) and is unique, so every
representation of the same MAC maps to exactly one label.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database.schema.base import Base


class ClientLabelRecord(Base):
    __tablename__ = "client_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Canonical normalized MAC (lowercase, colon-separated); unique identity.
    mac_address: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_client_labels_mac_address", "mac_address"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClientLabelRecord mac={self.mac_address!r} label={self.label!r}>"
