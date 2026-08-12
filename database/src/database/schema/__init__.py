"""Database schema (SQLAlchemy ORM models).

Import this package to register all models on `Base.metadata`.
"""

from database.schema.app_user import AppUserRecord
from database.schema.base import Base
from database.schema.chat import ChatMessageRecord
from database.schema.client_label import ClientLabelRecord
from database.schema.metadata import SystemMetadata
from database.schema.router import RouterRecord

__all__ = [
    "AppUserRecord",
    "Base",
    "ChatMessageRecord",
    "ClientLabelRecord",
    "RouterRecord",
    "SystemMetadata",
]
