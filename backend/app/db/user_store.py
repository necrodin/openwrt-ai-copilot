"""Persistence for application user accounts (first-run setup + login).

The initial administrator exists at most once: ``insert_admin`` runs a single
atomic ``INSERT ... SELECT ... WHERE NOT EXISTS`` guarded by the table's
partial unique index on ``role = 'admin'``, so concurrent setup requests can
never create two administrators. ``username`` is unique regardless of role.

The store is injectable (:param:`session_factory`) so tests can target an
isolated database; the module-level :data:`store` binds the shared engine.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.passwords import hash_password, normalize_username
from database.schema.app_user import AppUserRecord
from database.session import SessionLocal


class UserStore:
    """CRUD over :class:`AppUserRecord` with setup-safe admin creation."""

    def __init__(self, *, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def count(self) -> int:
        with self._session_factory() as session:
            return session.query(AppUserRecord).count()

    def setup_required(self) -> bool:
        """First-run setup is required iff no application user exists yet."""
        return self.count() == 0

    def get_by_username(self, username: str) -> AppUserRecord | None:
        with self._session_factory() as session:
            return (
                session.query(AppUserRecord)
                .filter(AppUserRecord.username == username)
                .first()
            )

    def insert_admin(self, *, username: str, password_hash: str) -> bool:
        """Atomically create the initial administrator.

        The ``WHERE NOT EXISTS`` guard plus the partial unique index on
        ``role='admin'`` make this race-safe: exactly one concurrent caller
        succeeds. Returns ``True`` when the row was inserted, ``False`` when the
        table already held a user (fail closed).
        """
        statement = text(
            """
            INSERT INTO app_users (username, password_hash, role, created_at, updated_at)
            SELECT :username, :password_hash, 'admin', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM app_users)
            """
        )
        try:
            with self._session_factory() as session:
                result = session.execute(
                    statement,
                    {"username": username, "password_hash": password_hash},
                )
                session.commit()
                return (result.rowcount or 0) >= 1
        except IntegrityError:
            # The partial unique index rejected a second admin row
            # (simultaneous setup request) — fail closed.
            return False

    def insert_user(self, *, username: str, password_hash: str, role: str) -> bool:
        """Insert a non-initial user (used only by the legacy env bootstrap).

        Unlike :meth:`insert_admin` this is not guarded by "first user only" —
        it is the migration path for an existing installation's environment
        credentials. Raises :class:`IntegrityError` on a duplicate username or a
        second ``admin`` row; callers opt into that failure mode.
        """
        with self._session_factory() as session:
            record = AppUserRecord(
                username=username,
                password_hash=password_hash,
                role=role,
            )
            session.add(record)
            session.commit()
        return True


def bootstrap_env_credentials(store: UserStore | None = None) -> int:
    """Migration: seed stored users once from legacy ``AUTH_ADMIN_*`` / readonly env.

    Runs only when the users table is empty. If an admin username/password pair
    is configured in the environment it is hashed and stored as the initial
    admin account, so an installation upgraded from the env-credential
    implementation keeps its existing browser credentials on its first boot.
    The readonly pair is seeded too (when configured) so a read-only browser
    account is preserved. Once any user exists the stored accounts are
    authoritative and future env changes are ignored (never updates an existing
    record, and never stores a plaintext password).

    Returns the number of users created. Idempotent.
    """
    store = store or _default_store
    if not store.setup_required():
        return 0

    created = 0
    if settings.auth_admin_username and settings.auth_admin_password:
        try:
            store.insert_user(
                username=normalize_username(settings.auth_admin_username),
                password_hash=hash_password(settings.auth_admin_password),
                role="admin",
            )
            created += 1
        except IntegrityError:
            pass  # another process completed first-run setup concurrently
    if created and settings.auth_readonly_username and settings.auth_readonly_password:
        try:
            store.insert_user(
                username=normalize_username(settings.auth_readonly_username),
                password_hash=hash_password(settings.auth_readonly_password),
                role="readonly",
            )
            created += 1
        except IntegrityError:
            pass
    return created


_default_store = UserStore()
store = _default_store