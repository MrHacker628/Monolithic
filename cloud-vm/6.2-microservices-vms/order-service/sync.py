"""
Database sync between the microservices.

The PRODUCT service owns the product data (master copy in its own database).
The CART and ORDER services each keep a REPLICA of the product data
(id, name, price, stock...) in THEIR OWN databases, so they can work without
asking the product service on every request.

The replicas are kept in sync two ways:
  1. PUSH: whenever a product changes (price edit, stock reduced after an order),
     the product service immediately sends the changed rows to
     POST /sync/products on the cart and order services.
  2. PULL: every SYNC_INTERVAL seconds the cart and order services also fetch the
     full product list and fix any differences (e.g. if they were down during a push).

GET /sync/status on each service returns a checksum of its product data.
When all three checksums are equal, the databases are in sync.
"""
import hashlib
import os
import threading
import time
from datetime import datetime

import requests
from flask import jsonify, request

import db

SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", 30))
REPLICA_COLUMNS = ("id", "name", "category", "price", "stock", "icon", "updated_at")

_last_sync = {"time": None, "how": None, "ok": None}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def checksum(rows):
    """Fingerprint of the product data that must match across databases."""
    text = "|".join(f"{r['id']}:{float(r['price']):.2f}:{int(r['stock'])}"
                    for r in sorted(rows, key=lambda r: r["id"]))
    return hashlib.md5(text.encode()).hexdigest()[:10]


def status_payload(service, table, extra=None):
    rows = db.query(f"SELECT id, name, price, stock, updated_at FROM {table} ORDER BY id")
    data = {
        "service": service,
        "database": db.DB_NAME,
        "table": table,
        "count": len(rows),
        "checksum": checksum(rows),
        "last_updated": max((r["updated_at"] for r in rows), default=None),
        "products": [{"id": r["id"], "name": r["name"], "price": float(r["price"]),
                      "stock": int(r["stock"])} for r in rows],
    }
    data.update(extra or {})
    return data


# ---------------------------------------------------------------- replica side (cart + order services)
def init_replica_table():
    db.execute("""CREATE TABLE IF NOT EXISTS product_replica (
        id INT PRIMARY KEY, name VARCHAR(100), category VARCHAR(50), price DOUBLE,
        stock INT, icon VARCHAR(16), updated_at VARCHAR(20))""")


def upsert_replica(products):
    # REPLACE INTO works on both MySQL and SQLite: insert, or overwrite the row with the same id
    db.executemany(f"REPLACE INTO product_replica ({','.join(REPLICA_COLUMNS)}) VALUES (?,?,?,?,?,?,?)",
                   [tuple(p[c] for c in REPLICA_COLUMNS) for p in products])


def pull_full_sync(product_service_url):
    try:
        products = requests.get(f"{product_service_url}/products", timeout=5).json()
        upsert_replica(products)
        _last_sync.update(time=now(), how="pull (full)", ok=True)
        return True
    except (requests.RequestException, ValueError):
        _last_sync.update(time=now(), how="pull (full)", ok=False)
        return False


def start_background_sync(product_service_url):
    def loop():
        # On startup retry quickly until the product service is reachable
        while not pull_full_sync(product_service_url):
            time.sleep(5)
        while True:
            time.sleep(SYNC_INTERVAL)
            pull_full_sync(product_service_url)
    threading.Thread(target=loop, daemon=True).start()


def register_replica_routes(app, service_name):
    @app.post("/sync/products")
    def receive_push():
        products = request.get_json(force=True).get("products", [])
        upsert_replica(products)
        _last_sync.update(time=now(), how=f"push ({len(products)} product(s))", ok=True)
        return jsonify(received=len(products))

    @app.get("/sync/status")
    def sync_status():
        return jsonify(status_payload(service_name, "product_replica",
                                      {"role": "replica", "last_sync": dict(_last_sync)}))


# ---------------------------------------------------------------- master side (product service)
def push_to_subscribers(products, subscribers):
    """Send changed products to every replica, in the background."""
    def send():
        for url in subscribers:
            try:
                requests.post(f"{url}/sync/products", json={"products": products}, timeout=5)
            except requests.RequestException:
                pass  # that replica is down; it will catch up with its next full pull
    threading.Thread(target=send, daemon=True).start()
