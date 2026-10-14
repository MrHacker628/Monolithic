"""
Cart Service (port 5002)
Owns shopping carts. Has its own database: cart.db
Calls the Product Service over HTTP to get product names and prices.
"""
import os
import sqlite3

import requests
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cart.db")
PORT = int(os.environ.get("PORT", 5002))
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001")

app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS cart_items (
            cart_id TEXT, product_id INTEGER, quantity INTEGER,
            PRIMARY KEY (cart_id, product_id))""")


def build_cart(cart_id):
    """Return the cart with product details fetched from the Product Service."""
    with db() as conn:
        rows = conn.execute("SELECT product_id, quantity FROM cart_items WHERE cart_id = ?",
                            (cart_id,)).fetchall()
    if not rows:
        return {"cart_id": cart_id, "items": [], "total": 0, "count": 0}
    qty = {r["product_id"]: r["quantity"] for r in rows}
    ids = ",".join(str(i) for i in qty)
    products = requests.get(f"{PRODUCT_SERVICE_URL}/products", params={"ids": ids}, timeout=5).json()
    items, total = [], 0
    for p in products:
        subtotal = p["price"] * qty[p["id"]]
        total += subtotal
        items.append({"product": p, "quantity": qty[p["id"]], "subtotal": subtotal})
    return {"cart_id": cart_id, "items": items, "total": total, "count": sum(qty.values())}


@app.get("/")
def home():
    """This is an API service, not a web page. Open the shop at http://localhost:5000"""
    return jsonify(service="cart-service", message="This is a REST API. Open the shop at http://localhost:5000",
                   endpoints=["GET /cart/<cart_id>", "POST /cart/<cart_id>/items", "PUT /cart/<cart_id>/items/<product_id>", "DELETE /cart/<cart_id>/items/<product_id>", "DELETE /cart/<cart_id>", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="cart-service", status="UP")


@app.get("/cart/<cart_id>")
def get_cart(cart_id):
    return jsonify(build_cart(cart_id))


@app.post("/cart/<cart_id>/items")
def add_item(cart_id):
    data = request.get_json(force=True)
    pid, quantity = int(data["product_id"]), max(1, int(data.get("quantity", 1)))
    # Check the product exists in the Product Service before adding it
    r = requests.get(f"{PRODUCT_SERVICE_URL}/products/{pid}", timeout=5)
    if r.status_code != 200:
        return jsonify(error="Product not found"), 404
    with db() as conn:
        conn.execute("""INSERT INTO cart_items VALUES (?,?,?)
                        ON CONFLICT(cart_id, product_id) DO UPDATE SET quantity = quantity + ?""",
                     (cart_id, pid, quantity, quantity))
    return jsonify(build_cart(cart_id)), 201


@app.put("/cart/<cart_id>/items/<int:pid>")
def update_item(cart_id, pid):
    quantity = int(request.get_json(force=True).get("quantity", 1))
    with db() as conn:
        if quantity <= 0:
            conn.execute("DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, pid))
        else:
            conn.execute("UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?",
                         (quantity, cart_id, pid))
    return jsonify(build_cart(cart_id))


@app.delete("/cart/<cart_id>/items/<int:pid>")
def remove_item(cart_id, pid):
    with db() as conn:
        conn.execute("DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, pid))
    return jsonify(build_cart(cart_id))


@app.delete("/cart/<cart_id>")
def clear_cart(cart_id):
    with db() as conn:
        conn.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
    return jsonify(cart_id=cart_id, items=[], total=0, count=0)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
