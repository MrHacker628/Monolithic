"""
Product Service - runs on product-vm (port 5001), INTERNAL IP only.
Owns the MASTER copy of the product catalogue in its own MySQL database (productdb).
Every change is pushed to the replicas in the cart and order databases (see sync.py).
"""
import os
import socket

from flask import Flask, jsonify, request

import db
import sync

PORT = int(os.environ.get("PORT", 5001))
# Internal URLs of the services that keep a replica of the product data
SUBSCRIBERS = [u.strip() for u in os.environ.get("SYNC_SUBSCRIBERS", "").split(",") if u.strip()]

app = Flask(__name__)

SEED_PRODUCTS = [
    (1, "Wireless Headphones", "Electronics", 2499, 25, "Over-ear Bluetooth headphones with 30-hour battery and deep bass.", "🎧"),
    (2, "Smart Watch", "Electronics", 3999, 25, "Fitness tracking, heart-rate monitor and notifications on your wrist.", "⌚"),
    (3, "Bluetooth Speaker", "Electronics", 1799, 25, "Portable waterproof speaker with 12-hour playtime.", "🔊"),
    (4, "Running Shoes", "Fashion", 2999, 25, "Lightweight cushioned shoes built for daily runs.", "👟"),
    (5, "Denim Jacket", "Fashion", 1999, 25, "Classic blue denim jacket, regular fit.", "🧥"),
    (6, "Backpack", "Accessories", 1299, 25, "25L laptop backpack with padded compartment.", "🎒"),
    (7, "Sunglasses", "Accessories", 899, 25, "UV400 polarised sunglasses.", "🕶️"),
    (8, "Coffee Mug", "Home", 349, 25, "350ml ceramic mug, microwave safe.", "☕"),
    (9, "Desk Lamp", "Home", 1149, 25, "LED desk lamp with 3 brightness levels.", "💡"),
    (10, "Python Programming Book", "Books", 699, 25, "Beginner-friendly guide to Python programming.", "📘"),
]


def init_db():
    db.execute("""CREATE TABLE IF NOT EXISTS products (
        id INT PRIMARY KEY, name VARCHAR(100) NOT NULL, category VARCHAR(50) NOT NULL,
        price DOUBLE NOT NULL, stock INT NOT NULL, description VARCHAR(255), icon VARCHAR(16),
        updated_at VARCHAR(20))""")
    if db.query("SELECT COUNT(*) AS n FROM products", one=True)["n"] == 0:
        ts = sync.now()
        db.executemany("""INSERT INTO products (id, name, category, price, stock, description, icon, updated_at)
                          VALUES (?,?,?,?,?,?,?,?)""", [p + (ts,) for p in SEED_PRODUCTS])


def get(pid):
    return db.query("SELECT * FROM products WHERE id = ?", (pid,), one=True)


def changed(pids):
    """Push the latest version of these products to the cart and order databases."""
    rows = db.query(f"SELECT * FROM products WHERE id IN ({','.join('?' * len(pids))})", pids)
    sync.push_to_subscribers(rows, SUBSCRIBERS)


@app.get("/")
def home():
    return jsonify(service="product-service", message="Internal REST API. The shop is served by the gateway VM.",
                   endpoints=["GET /products?q=&category=&ids=", "GET /products/<id>", "GET /categories",
                              "PUT /products/<id>", "POST /products/<id>/reduce-stock", "GET /sync/status",
                              "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="product-service", status="UP", host=socket.gethostname(), database=db.DB_NAME)


@app.get("/products")
def list_products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    ids = request.args.get("ids", "").strip()
    sql, params = "SELECT * FROM products WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
        params += [f"%{q}%"] * 3
    if category:
        sql += " AND category = ?"
        params.append(category)
    if ids:
        id_list = [int(i) for i in ids.split(",") if i.isdigit()]
        if not id_list:
            return jsonify([])
        sql += f" AND id IN ({','.join('?' * len(id_list))})"
        params += id_list
    return jsonify(db.query(sql + " ORDER BY id", params))


@app.get("/products/<int:pid>")
def get_product(pid):
    p = get(pid)
    return (jsonify(p), 200) if p else (jsonify(error="Product not found"), 404)


@app.get("/categories")
def categories():
    return jsonify([r["category"] for r in db.query("SELECT DISTINCT category FROM products ORDER BY category")])


@app.put("/products/<int:pid>")
def update_product(pid):
    """Admin: change price and/or stock. The change is synced to the other databases."""
    if not get(pid):
        return jsonify(error="Product not found"), 404
    data = request.get_json(force=True)
    if "price" in data:
        db.execute("UPDATE products SET price = ?, updated_at = ? WHERE id = ?", (float(data["price"]), sync.now(), pid))
    if "stock" in data:
        db.execute("UPDATE products SET stock = ?, updated_at = ? WHERE id = ?", (int(data["stock"]), sync.now(), pid))
    changed([pid])
    return jsonify(get(pid))


@app.post("/products/<int:pid>/reduce-stock")
def reduce_stock(pid):
    """Called by the order service after a successful payment."""
    qty = int(request.get_json(force=True).get("quantity", 1))
    p = get(pid)
    if not p:
        return jsonify(error="Product not found"), 404
    db.execute("UPDATE products SET stock = ?, updated_at = ? WHERE id = ?",
               (max(0, int(p["stock"]) - qty), sync.now(), pid))
    changed([pid])
    return jsonify(get(pid))


@app.get("/sync/status")
def sync_status():
    return jsonify(sync.status_payload("product-service", "products",
                                       {"role": "master", "subscribers": SUBSCRIBERS}))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
