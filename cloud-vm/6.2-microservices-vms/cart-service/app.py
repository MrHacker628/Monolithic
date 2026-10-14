"""
Cart Service - runs on cart-vm (port 5002), INTERNAL IP only.
Own MySQL database (cartdb) with:
  cart_items       - what is in each shopper's cart
  product_replica  - a synced copy of the product data (names, prices, stock)
Prices and stock come from the local replica, so the cart keeps working
even if the product service is briefly unavailable.
"""
import os
import socket

from flask import Flask, jsonify, request

import db
import sync

PORT = int(os.environ.get("PORT", 5002))
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001")

app = Flask(__name__)


def init_db():
    db.execute("""CREATE TABLE IF NOT EXISTS cart_items (
        cart_id VARCHAR(64), product_id INT, quantity INT, PRIMARY KEY (cart_id, product_id))""")
    sync.init_replica_table()


def build_cart(cart_id):
    rows = db.query("""SELECT c.product_id, c.quantity, p.name, p.category, p.price, p.stock, p.icon
                       FROM cart_items c JOIN product_replica p ON p.id = c.product_id
                       WHERE c.cart_id = ? ORDER BY c.product_id""", (cart_id,))
    items, total = [], 0
    for r in rows:
        product = {"id": r["product_id"], "name": r["name"], "category": r["category"],
                   "price": float(r["price"]), "stock": int(r["stock"]), "icon": r["icon"]}
        subtotal = product["price"] * r["quantity"]
        total += subtotal
        items.append({"product": product, "quantity": r["quantity"], "subtotal": subtotal})
    return {"cart_id": cart_id, "items": items, "total": total, "count": sum(i["quantity"] for i in items)}


@app.get("/")
def home():
    return jsonify(service="cart-service", message="Internal REST API. The shop is served by the gateway VM.",
                   endpoints=["GET /cart/<cart_id>", "POST /cart/<cart_id>/items",
                              "PUT /cart/<cart_id>/items/<product_id>", "DELETE /cart/<cart_id>/items/<product_id>",
                              "DELETE /cart/<cart_id>", "POST /sync/products", "GET /sync/status", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="cart-service", status="UP", host=socket.gethostname(), database=db.DB_NAME)


@app.get("/cart/<cart_id>")
def get_cart(cart_id):
    return jsonify(build_cart(cart_id))


@app.post("/cart/<cart_id>/items")
def add_item(cart_id):
    data = request.get_json(force=True)
    pid, qty = int(data["product_id"]), max(1, int(data.get("quantity", 1)))
    product = db.query("SELECT * FROM product_replica WHERE id = ?", (pid,), one=True)
    if not product:
        return jsonify(error="Product not found"), 404
    existing = db.query("SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, pid), one=True)
    new_qty = qty + (existing["quantity"] if existing else 0)
    if new_qty > int(product["stock"]):
        return jsonify(error=f"Only {product['stock']} left in stock for {product['name']}."), 409
    if existing:
        db.execute("UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?", (new_qty, cart_id, pid))
    else:
        db.execute("INSERT INTO cart_items (cart_id, product_id, quantity) VALUES (?,?,?)", (cart_id, pid, qty))
    return jsonify(build_cart(cart_id)), 201


@app.put("/cart/<cart_id>/items/<int:pid>")
def update_item(cart_id, pid):
    qty = int(request.get_json(force=True).get("quantity", 1))
    if qty <= 0:
        db.execute("DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, pid))
    else:
        product = db.query("SELECT * FROM product_replica WHERE id = ?", (pid,), one=True)
        if product and qty > int(product["stock"]):
            return jsonify(error=f"Only {product['stock']} left in stock for {product['name']}."), 409
        db.execute("UPDATE cart_items SET quantity = ? WHERE cart_id = ? AND product_id = ?", (qty, cart_id, pid))
    return jsonify(build_cart(cart_id))


@app.delete("/cart/<cart_id>/items/<int:pid>")
def remove_item(cart_id, pid):
    db.execute("DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, pid))
    return jsonify(build_cart(cart_id))


@app.delete("/cart/<cart_id>")
def clear_cart(cart_id):
    db.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
    return jsonify(cart_id=cart_id, items=[], total=0, count=0)


init_db()
sync.register_replica_routes(app, "cart-service")
sync.start_background_sync(PRODUCT_SERVICE_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
