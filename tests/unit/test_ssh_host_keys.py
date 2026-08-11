"""Host-key verification regression tests.

Covers the persisted known-hosts trust store and the guarantee that both SSH
backends route every host-key decision through the same logic:

1. a trusted host key is accepted,
2. unknown host keys are recorded under TOFU (and rejected under ``reject``),
3. a changed host key is rejected (fail closed),
4. a router IP change with the same host key keeps working,
5. both SSH backends behave consistently.

No real SSH connection is attempted; the decision layer (:func:`verify_host_key`
and :class:`HostKeyStore`) and each backend's host-key hook are exercised
directly.
"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from router_agent.transport.ssh.backends import (
    _asyncssh_host_key_client,
    _ParamikoHostKeyPolicy,
)
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.errors import HostKeyError
from router_agent.transport.ssh.host_keys import (
    MISMATCH,
    TRUSTED,
    UNKNOWN,
    HostKeyStore,
    default_known_hosts_path,
    host_key_settings,
    verify_host_key,
)

HOST = "192.168.1.1"
PORT = 22
KEY_TYPE = "ssh-ed25519"
BLOB_A = base64.b64encode(b"A" * 32).decode("ascii")
BLOB_B = base64.b64encode(b"B" * 32).decode("ascii")


def _config(**kwargs) -> SSHConfig:
    defaults = {"host": HOST, "credentials": SSHCredentials(username="root")}
    return SSHConfig(**(defaults | kwargs))


@pytest.fixture()
def store(tmp_path: Path) -> HostKeyStore:
    return HostKeyStore(tmp_path / "known_hosts")


# =============================================================================
# 1. trusted host key accepted
# =============================================================================


def test_trusted_host_key_accepted(store: HostKeyStore) -> None:
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == TRUSTED
    accepted, reason = verify_host_key(store, HOST, PORT, KEY_TYPE, BLOB_A, allow_tou=True)
    assert accepted is True
    assert reason is None
    # trusted keys stay accepted even under the strict policy
    accepted, _ = verify_host_key(store, HOST, PORT, KEY_TYPE, BLOB_A, allow_tou=False)
    assert accepted is True


def test_trusted_key_survives_store_reload(tmp_path: Path) -> None:
    path = tmp_path / "known_hosts"
    HostKeyStore(path).record(HOST, PORT, KEY_TYPE, BLOB_A)
    reloaded = HostKeyStore(path)
    assert reloaded.check(HOST, PORT, KEY_TYPE, BLOB_A) == TRUSTED


# =============================================================================
# 2. unknown host key behavior
# =============================================================================


def test_unknown_host_key_tou_records_and_accepts(store: HostKeyStore) -> None:
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == UNKNOWN
    accepted, reason = verify_host_key(store, HOST, PORT, KEY_TYPE, BLOB_A, allow_tou=True)
    assert accepted is True
    assert reason is None
    # recorded by TOFU, so the next connection is trusted without re-consent
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == TRUSTED


def test_unknown_host_key_reject_policy_denies(store: HostKeyStore) -> None:
    accepted, reason = verify_host_key(store, HOST, PORT, KEY_TYPE, BLOB_A, allow_tou=False)
    assert accepted is False
    assert "not trusted" in (reason or "")
    # a rejected key is never recorded
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == UNKNOWN


def test_unknown_host_key_on_second_port_is_still_unknown(store: HostKeyStore) -> None:
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    assert store.check(HOST, 2222, KEY_TYPE, BLOB_A) == UNKNOWN


# =============================================================================
# 3. changed host key rejected
# =============================================================================


def test_changed_host_key_rejected_even_with_tou(store: HostKeyStore) -> None:
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_B) == MISMATCH
    accepted, reason = verify_host_key(store, HOST, PORT, KEY_TYPE, BLOB_B, allow_tou=True)
    assert accepted is False
    assert "has changed" in (reason or "")
    # the changed key is never recorded over the trusted one
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == TRUSTED
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_B) == MISMATCH


# =============================================================================
# 4. router IP change with the same host key
# =============================================================================


def test_router_ip_change_with_same_key_keeps_working(store: HostKeyStore) -> None:
    store.record("192.168.1.1", PORT, KEY_TYPE, BLOB_A)
    # the router moves to a new IP but keeps its host key: TOFU accepts the new
    # host and the same key is trusted under the new address
    accepted, _ = verify_host_key(store, "192.168.1.42", PORT, KEY_TYPE, BLOB_A, allow_tou=True)
    assert accepted is True
    assert store.check("192.168.1.42", PORT, KEY_TYPE, BLOB_A) == TRUSTED
    # the old address is still trusted too
    assert store.check("192.168.1.1", PORT, KEY_TYPE, BLOB_A) == TRUSTED


# =============================================================================
# 5. both SSH backends behaving consistently
# =============================================================================


def _asyncssh_stub_key(blob: bytes, algorithm: bytes = b"ssh-ed25519") -> SimpleNamespace:
    return SimpleNamespace(algorithm=algorithm, encode_ssh_public=lambda: blob)


def _paramiko_stub_key(blob: bytes, key_type: str = "ssh-ed25519") -> SimpleNamespace:
    return SimpleNamespace(get_name=lambda: key_type, asbytes=lambda: blob)


def _asyncssh_client(store: HostKeyStore, *, allow_tou: bool):
    import asyncssh

    factory = _asyncssh_host_key_client(asyncssh, store, allow_tou=allow_tou)
    return factory()


def _paramiko_policy(store: HostKeyStore, *, allow_tou: bool) -> _ParamikoHostKeyPolicy:
    return _ParamikoHostKeyPolicy(store, allow_tou=allow_tou, host=HOST, port=PORT)


def test_backends_accept_unknown_key_and_trust_each_other(store: HostKeyStore) -> None:
    asyncssh_client = _asyncssh_client(store, allow_tou=True)
    paramiko_policy = _paramiko_policy(store, allow_tou=True)

    blob = b"Z" * 32
    assert asyncssh_client.validate_host_public_key(
        HOST, HOST, PORT, _asyncssh_stub_key(blob)
    ) is True
    assert paramiko_policy.missing_host_key(None, HOST, _paramiko_stub_key(blob)) is None
    # both backends recorded the same key identity
    assert store.check(HOST, PORT, KEY_TYPE, base64.b64encode(blob).decode()) == TRUSTED


def test_backends_reject_changed_key_identically(store: HostKeyStore) -> None:
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    asyncssh_client = _asyncssh_client(store, allow_tou=True)
    paramiko_policy = _paramiko_policy(store, allow_tou=True)

    blob = b"C" * 32
    assert asyncssh_client.validate_host_public_key(
        HOST, HOST, PORT, _asyncssh_stub_key(blob)
    ) is False
    with pytest.raises(HostKeyError, match="has changed"):
        paramiko_policy.missing_host_key(None, HOST, _paramiko_stub_key(blob))
    assert store.check(HOST, PORT, KEY_TYPE, BLOB_A) == TRUSTED


def test_backends_reject_unknown_key_under_strict_policy(store: HostKeyStore) -> None:
    asyncssh_client = _asyncssh_client(store, allow_tou=False)
    paramiko_policy = _paramiko_policy(store, allow_tou=False)

    blob = b"Q" * 32
    assert asyncssh_client.validate_host_public_key(
        HOST, HOST, PORT, _asyncssh_stub_key(blob)
    ) is False
    with pytest.raises(HostKeyError, match="not trusted"):
        paramiko_policy.missing_host_key(None, HOST, _paramiko_stub_key(blob))
    assert store.check(HOST, PORT, KEY_TYPE, base64.b64encode(blob).decode()) == UNKNOWN


# =============================================================================
# store + settings helpers
# =============================================================================


def test_record_is_idempotent(tmp_path: Path) -> None:
    store = HostKeyStore(tmp_path / "known_hosts")
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    store.record(HOST, PORT, KEY_TYPE, BLOB_A)
    assert len(store.trusted_keys(HOST, PORT)) == 1


def test_store_file_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "known_hosts"
    HostKeyStore(path).record(HOST, PORT, KEY_TYPE, BLOB_A)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_default_known_hosts_path_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "kh"
    monkeypatch.setenv("OPENWRT_AI_KNOWN_HOSTS", str(override))
    assert default_known_hosts_path() == override


@pytest.mark.parametrize(
    "policy, expected_tou",
    [
        ("auto", True),
        ("reject", False),
    ],
)
def test_host_key_settings_auto_and_reject_use_persisted_store(
    policy: str, expected_tou: bool
) -> None:
    store, allow_tou = host_key_settings(_config(host_key_policy=policy))
    assert allow_tou is expected_tou
    assert isinstance(store, HostKeyStore)


def test_host_key_settings_known_hosts_and_system_are_library_handled() -> None:
    store, allow_tou = host_key_settings(_config(host_key_policy="reject", known_hosts=Path("/x")))
    assert store is None
    assert allow_tou is False
    store, allow_tou = host_key_settings(_config(host_key_policy="system"))
    assert store is None
    assert allow_tou is False
