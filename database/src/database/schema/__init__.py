"""Database schema (SQLAlchemy ORM models).

Import this package to register all models on `Base.metadata`.
"""

from database.schema.base import Base
from database.schema.chat import ChatMessageRecord
from database.schema.metadata import SystemMetadata

__all__ = ["Base", "ChatMessageRecord", "SystemMetadata"]
