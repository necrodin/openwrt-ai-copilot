"""OpenWrt AI Copilot — data layer.

Owns the SQLite engine, session factory, schema (SQLAlchemy ORM models), and
(plan) migrations. Nothing in this package imports application or AI code.
"""

__version__ = "0.1.0"

from database.schema import Base, SystemMetadata
from database.session import SessionLocal, engine, init_db

__all__ = ["Base", "SessionLocal", "SystemMetadata", "engine", "init_db"]
