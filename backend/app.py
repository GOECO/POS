"""GOECO POS AI: deliberately small single-store MVP, not a production SaaS."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from collections import defaultdict
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    unit_price_vnd: int = Field(ge=0)
    stock: int = Field(ge=0)


class OrderLine(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10000)


class CheckoutInput(BaseModel):
    items: list[OrderLine] = Field(min_length=1, max_length=100)
    payment_method: Literal["cash", "bank_transfer"]
    cash_received_vnd: int | None = Field(default=None, ge=0)


def create_app(db_path: str | None = None, api_key: str | None = None) -> FastAPI:
    database = db_path or os.getenv("POS_DB_PATH", str(ROOT / "data" / "pos.sqlite3"))
    secret = api_key if api_key is not None else os.getenv("POS_API_KEY", "")
    Path(database).parent.mkdir(parents=True, exist_ok=True)

    def connect() -> sqlite3.Connection:
        db = sqlite3.connect(database, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    with closing(connect()) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                unit_price_vnd INTEGER NOT NULL CHECK (unit_price_vnd >= 0),
                stock INTEGER NOT NULL CHECK (stock >= 0)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                request_hash TEXT NOT NULL,
                total_vnd INTEGER NOT NULL CHECK (total_vnd >= 0),
                payment_method TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                cash_received_vnd INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price_vnd INTEGER NOT NULL
            );
        """)

    @contextmanager
    def transaction():
        db = connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def require_key(authorization: Annotated[str | None, Header()] = None) -> None:
        supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
        if not secret or not hmac.compare_digest(supplied, secret):
            raise HTTPException(status_code=401, detail="Invalid or missing POS API key")

    app = FastAPI(title="GOECO POS AI", version="0.1.0")

    @app.get("/")
    def home():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "goeco-pos-ai"}

    @app.get("/v1/products", dependencies=[Depends(require_key)])
    def list_products():
        with closing(connect()) as db:
            return [dict(r) for r in db.execute(
                "SELECT id,sku,name,unit_price_vnd,stock FROM products ORDER BY id DESC"
            ).fetchall()]

    @app.post("/v1/products", status_code=201, dependencies=[Depends(require_key)])
    def add_product(item: ProductInput):
        try:
            with transaction() as db:
                cur = db.execute(
                    "INSERT INTO products(sku,name,unit_price_vnd,stock) VALUES(?,?,?,?)",
                    (item.sku, item.name.strip(), item.unit_price_vnd, item.stock),
                )
                product_id = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="SKU already exists")
        return {"id": product_id, **item.model_dump()}

    @app.get("/v1/orders", dependencies=[Depends(require_key)])
    def list_orders():
        with closing(connect()) as db:
            return [dict(r) for r in db.execute(
                "SELECT id,total_vnd,payment_method,payment_status,created_at "
                "FROM orders ORDER BY id DESC LIMIT 100"
            ).fetchall()]

    @app.post("/v1/orders", status_code=201, dependencies=[Depends(require_key)])
    def checkout(
        payload: CheckoutInput,
        idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
    ):
        request_hash = hashlib.sha256(
            payload.model_dump_json(exclude_none=True).encode("utf-8")
        ).hexdigest()
        grouped: dict[int, int] = defaultdict(int)
        for item in payload.items:
            grouped[item.product_id] += item.quantity

        with transaction() as db:
            existing = db.execute(
                "SELECT * FROM orders WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise HTTPException(status_code=409, detail="Idempotency key reused for another request")
                return {**dict(existing), "replayed": True}

            order_lines = []
            total = 0
            for product_id, quantity in grouped.items():
                product = db.execute(
                    "SELECT id,unit_price_vnd,stock FROM products WHERE id=?", (product_id,)
                ).fetchone()
                if not product:
                    raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
                if product["stock"] < quantity:
                    raise HTTPException(status_code=409, detail=f"Insufficient stock for product {product_id}")
                total += product["unit_price_vnd"] * quantity
                order_lines.append((product_id, quantity, product["unit_price_vnd"]))

            if payload.payment_method == "cash":
                if payload.cash_received_vnd is None or payload.cash_received_vnd < total:
                    raise HTTPException(status_code=422, detail="Insufficient cash received")
                # Cash recorded by a cashier. NOT verification by an external payment provider.
                status = "cash_recorded"
            else:
                if payload.cash_received_vnd is not None:
                    raise HTTPException(status_code=422, detail="Cash amount forbidden for bank transfer")
                status = "pending"

            cur = db.execute(
                "INSERT INTO orders(idempotency_key,request_hash,total_vnd,payment_method,"
                "payment_status,cash_received_vnd) VALUES(?,?,?,?,?,?)",
                (idempotency_key, request_hash, total, payload.payment_method, status,
                 payload.cash_received_vnd),
            )
            order_id = cur.lastrowid
            for pid, qty, price in order_lines:
                db.execute(
                    "UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                    (qty, pid, qty),
                )
                db.execute(
                    "INSERT INTO order_items(order_id,product_id,quantity,unit_price_vnd)"
                    " VALUES(?,?,?,?)", (order_id, pid, qty, price),
                )
            return {
                "id": order_id, "total_vnd": total, "payment_method": payload.payment_method,
                "payment_status": status, "replayed": False,
            }

    return app


app = create_app()
