import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(str(Path(directory) / "test.sqlite3"), api_key="unit-test-secret")
        with TestClient(app) as c:
            yield c


HEADERS = {"Authorization": "Bearer unit-test-secret"}


def product(client, sku="CAPHE", stock=3, price=25000):
    response = client.post(
        "/v1/products", headers=HEADERS,
        json={"sku": sku, "name": "Cà phê", "stock": stock, "unit_price_vnd": price},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def checkout(client, product_id, qty=1, method="cash", received=100000, key="unique-key-123"):
    payload = {"items": [{"product_id": product_id, "quantity": qty}],
               "payment_method": method}
    if method == "cash":
        payload["cash_received_vnd"] = received
    return client.post(
        "/v1/orders", json=payload,
        headers={**HEADERS, "Idempotency-Key": key},
    )


def test_auth_and_health(client):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/products").status_code == 401
    assert client.get("/v1/products", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_product_unique_sku(client):
    product(client)
    response = client.post(
        "/v1/products", headers=HEADERS,
        json={"sku": "CAPHE", "name": "Another", "stock": 1, "unit_price_vnd": 1},
    )
    assert response.status_code == 409


def test_cash_checkout_and_replay_only_decrements_once(client):
    pid = product(client)
    first = checkout(client, pid, qty=2)
    assert first.status_code == 201, first.text
    assert first.json()["total_vnd"] == 50000
    assert first.json()["payment_status"] == "cash_recorded"
    second = checkout(client, pid, qty=2)
    assert second.status_code == 201
    assert second.json()["replayed"] is True
    inventory = client.get("/v1/products", headers=HEADERS).json()
    assert inventory[0]["stock"] == 1


def test_stock_rejection_rolls_back(client):
    pid = product(client, stock=1)
    response = checkout(client, pid, qty=2)
    assert response.status_code == 409
    assert client.get("/v1/products", headers=HEADERS).json()[0]["stock"] == 1


def test_cash_shortage_rolls_back(client):
    pid = product(client)
    response = checkout(client, pid, received=100)
    assert response.status_code == 422
    assert client.get("/v1/products", headers=HEADERS).json()[0]["stock"] == 3


def test_transfer_stays_pending(client):
    pid = product(client)
    response = checkout(client, pid, method="bank_transfer")
    assert response.status_code == 201
    assert response.json()["payment_status"] == "pending"


def test_conflicting_idempotency_key(client):
    pid = product(client)
    assert checkout(client, pid, qty=1).status_code == 201
    assert checkout(client, pid, qty=2).status_code == 409
