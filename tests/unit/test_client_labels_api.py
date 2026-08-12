"""Client device-label API and store regression tests.

Covers create/read/update/delete, MAC normalization, admin-vs-readonly scopes,
persistence across store reloads, and that unlabeled clients / unknown MACs are
never auto-created. The "label merged into client response / search matches
label / persists across IP changes" behaviors are asserted in the frontend
regression tests (``frontend/tests/client-labels.test.mjs``), which exercise
the real ``lib/clients.ts`` logic that builds the client representation.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.client_label_store import ClientLabelStore, normalize_mac
from database.schema.base import Base
from tests.auth import admin_headers, readonly_headers


def _labels(client, mac: str | None = None) -> list[dict]:
    response = client.get("/api/v1/clients/labels")
    assert response.status_code == 200, response.text
    return response.json()["labels"]


def test_create_label(client) -> None:
    response = client.put(
        "/api/v1/clients/labels/AA:BB:CC:11:22:33",
        json={"label": "Talat iPhone"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mac_address"] == "aa:bb:cc:11:22:33"
    assert body["label"] == "Talat iPhone"
    assert body["created_at"]
    assert body["updated_at"]


def test_read_label(client) -> None:
    client.put("/api/v1/clients/labels/aa:bb:cc:11:22:33", json={"label": "Talat iPhone"})
    labels = _labels(client)
    assert len(labels) == 1
    assert labels[0]["mac_address"] == "aa:bb:cc:11:22:33"
    assert labels[0]["label"] == "Talat iPhone"


def test_update_label(client) -> None:
    client.put("/api/v1/clients/labels/aa:bb:cc:11:22:33", json={"label": "Talat iPhone"})
    response = client.put(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        json={"label": "Talat's Phone"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Talat's Phone"
    labels = _labels(client)
    assert len(labels) == 1  # same MAC, no duplicate row
    assert labels[0]["label"] == "Talat's Phone"


def test_duplicate_mac_updates_existing_label(client) -> None:
    client.put("/api/v1/clients/labels/aa:bb:cc:11:22:33", json={"label": "PS5"})
    response = client.put(
        "/api/v1/clients/labels/AA-BB-CC-11-22-33",  # same device, dashed form
        json={"label": "PlayStation 5"},
    )
    assert response.status_code == 200, response.text
    labels = _labels(client)
    assert len(labels) == 1
    assert labels[0]["label"] == "PlayStation 5"
    assert labels[0]["mac_address"] == "aa:bb:cc:11:22:33"


def test_delete_label(client) -> None:
    client.put("/api/v1/clients/labels/aa:bb:cc:11:22:33", json={"label": "PS5"})
    response = client.delete("/api/v1/clients/labels/aa:bb:cc:11:22:33")
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert _labels(client) == []
    # Deleting an unknown MAC is a 404, never an auto-created/guessed row.
    response = client.delete("/api/v1/clients/labels/aa:bb:cc:11:22:33")
    assert response.status_code == 404


def test_mac_normalization(client) -> None:
    for mac in (
        "AA-BB-CC-11-22-33",
        "AA:BB:CC:11:22:33",
        "aabbcc112233",
        "aa:bb:cc:11:22:33",
    ):
        response = client.put(f"/api/v1/clients/labels/{mac}", json={"label": "Salon TV"})
        assert response.status_code == 200, (mac, response.text)
        assert response.json()["mac_address"] == "aa:bb:cc:11:22:33"
    labels = _labels(client)
    assert len(labels) == 1  # every representation mapped to the same record


def test_invalid_mac_rejected(client) -> None:
    response = client.put(
        "/api/v1/clients/labels/not-a-mac",
        json={"label": "Bogus"},
    )
    assert response.status_code == 422


def test_empty_label_rejected(client) -> None:
    response = client.put(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        json={"label": "   "},
    )
    assert response.status_code == 422


def test_readonly_cannot_modify_labels(client) -> None:
    read_response = client.get("/api/v1/clients/labels", headers=readonly_headers())
    assert read_response.status_code == 200
    put_response = client.put(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        json={"label": "PS5"},
        headers=readonly_headers(),
    )
    assert put_response.status_code == 403
    delete_response = client.delete(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        headers=readonly_headers(),
    )
    assert delete_response.status_code == 403


def test_admin_can_modify_labels(client) -> None:
    response = client.put(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        json={"label": "PS5"},
        headers=admin_headers(),
    )
    assert response.status_code == 200, response.text
    labels = _labels(client)
    assert labels[0]["label"] == "PS5"
    delete_response = client.delete(
        "/api/v1/clients/labels/aa:bb:cc:11:22:33",
        headers=admin_headers(),
    )
    assert delete_response.status_code == 200


def test_unauthenticated_denied(client) -> None:
    """A request without any credential is rejected (fails closed)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as bare:
        response = bare.put(
            "/api/v1/clients/labels/aa:bb:cc:11:22:33",
            json={"label": "PS5"},
        )
    assert response.status_code == 401


def test_label_persists_when_ip_changes(tmp_path) -> None:
    """Identity is the MAC, so a label survives the device changing IP."""
    engine = create_engine(f"sqlite:///{tmp_path / 'labels.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    store = ClientLabelStore(factory)
    store.upsert(mac="aa:bb:cc:11:22:33", label="Talat iPhone")
    # The device moves to a new IP; nothing IP-related is stored, so the label
    # read by MAC is unchanged.
    assert store.get("aa:bb:cc:11:22:33").label == "Talat iPhone"
    assert store.get("AA:BB:CC:11:22:33").label == "Talat iPhone"


def test_labels_survive_application_restart(tmp_path) -> None:
    """A fresh store over the same database file reads persisted labels."""
    engine = create_engine(f"sqlite:///{tmp_path / 'restart.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)

    first = ClientLabelStore(factory)
    first.upsert(mac="AA:BB:CC:11:22:33", label="Talat iPhone")
    first.upsert(mac="DD:EE:FF:44:55:66", label="Salon TV")

    # New store instance = "application restart". Nothing is reloaded manually;
    # the rows are read straight back from the database file.
    second = ClientLabelStore(factory)
    labels = second.list_all()
    assert [entry.label for entry in labels] == ["Talat iPhone", "Salon TV"]
    assert all(entry.mac_address.islower() for entry in labels)


def test_store_upsert_normalizes_and_dedupes(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'upsert.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    store = ClientLabelStore(factory)
    store.upsert(mac="AA-BB-CC-11-22-33", label="one")
    store.upsert(mac="aabbcc112233", label="two")
    store.upsert(mac="AA:BB:CC:11:22:33", label="three")
    assert len(store.list_all()) == 1
    assert store.list_all()[0].label == "three"
    assert store.list_all()[0].mac_address == "aa:bb:cc:11:22:33"


def test_normalize_mac_unit() -> None:
    assert normalize_mac("AA:BB:CC:11:22:33") == "aa:bb:cc:11:22:33"
    assert normalize_mac("AA-BB-CC-11-22-33") == "aa:bb:cc:11:22:33"
    assert normalize_mac("AABBCC112233") == "aa:bb:cc:11:22:33"
    assert normalize_mac("aa:bb:cc:11:22:33") == "aa:bb:cc:11:22:33"
    assert normalize_mac("") is None
    assert normalize_mac("not-a-mac") is None
    assert normalize_mac("aa:bb:cc:11:22") is None
