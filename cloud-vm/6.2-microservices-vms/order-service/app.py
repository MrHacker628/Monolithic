"""
Order Service - runs on order-vm (port 5003), INTERNAL IP only.
Handles orders AND payments (mock card gateway, test mode).
Own MySQL database (orderdb) with:
  orders, order_items, payments
  product_replica  - a synced copy of the product data, used to check stock

Placing an order:
  1. get the cart from the cart service          (internal IP)
  2. check stock against the local product replica
  3. charge the card (mock gateway)
  4. tell the product service to reduce stock    (internal IP)
     -> the product service pushes the new stock to the cart and order databases
  5. clear the cart in the cart service          (internal IP)
"""
import os
import socket
import uuid

import requests
from flask import Flask, jsonify, request

import db
import sync

PORT = int(os.environ.get("PORT", 5003))
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001")
CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://localhost:5002")

app = Flask(__name__)


def init_db():
    db.execute("""CREATE TABLE IF NOT EXISTS orders (
        id VARCHAR(20) PRIMARY KEY, customer_name VARCHAR(100), email VARCHAR(100),
        address VARCHAR(255), total DOUBLE, status VARCHAR(20), created_at VARCHAR(20))""")
    db.execute("""CREATE TABLE IF NOT EXISTS order_items (
        order_id VARCHAR(20), product_id INT, name VARCHAR(100), price DOUBLE, quantity INT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS payments (
        id VARCHAR(20) PRIMARY KEY, order_id VARCHAR(20), amount DOUBLE, method VARCHAR(10),
        card_last4 VARCHAR(4), status VARCHAR(20), created_at VARCHAR(20))""")
    sync.init_replica_table()


def charge_card(order_id, amount, card, expiry, cvv):
    """Mock payment gateway. Any valid 16-digit card works; a card ending in 0000 is declined."""
    card = str(card).replace(" ", "")
    errors = []
    if not (card.isdigit() and len(card) == 16):
        errors.append("Card number must be 16 digits.")
    if len(expiry) != 5 or expiry[2] != "/":
        errors.append("Expiry must be in MM/YY format.")
    if not (cvv.isdigit() and len(cvv) == 3):
        errors.append("CVV must be 3 digits.")
    if errors:
        return None, errors
    status = "DECLINED" if card.endswith("0000") else "SUCCESS"
    payment = ("PAY-" + uuid.uuid4().hex[:8].upper(), order_id, amount, "CARD", card[-4:], status, sync.now())
    db.execute("INSERT INTO payments VALUES (?,?,?,?,?,?,?)", payment)
    return status, []


@app.get("/")
def home():
    return jsonify(service="order-service", message="Internal REST API. The shop is served by the gateway VM.",
                   endpoints=["POST /orders", "GET /orders", "GET /orders/<order_id>",
                              "POST /sync/products", "GET /sync/status", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="order-service", status="UP", host=socket.gethostname(), database=db.DB_NAME)


@app.post("/orders")
def place_order():
    data = request.get_json(force=True)
    name, email, address = (str(data.get(k, "")).strip() for k in ("name", "email", "address"))
    if not (name and email and address):
        return jsonify(errors=["Please fill in your name, email and address."]), 400

    # 1. cart from the cart service
    try:
        cart = requests.get(f"{CART_SERVICE_URL}/cart/{data['cart_id']}", timeout=5).json()
    except requests.RequestException:
        return jsonify(errors=["Cart service is not reachable."]), 503
    if not cart["items"]:
        return jsonify(errors=["Your cart is empty."]), 400

    # 2. stock check against the synced product replica in THIS service's database
    for item in cart["items"]:
        p = db.query("SELECT name, stock FROM product_replica WHERE id = ?", (item["product"]["id"],), one=True)
        if not p or int(p["stock"]) < item["quantity"]:
            left = int(p["stock"]) if p else 0
            return jsonify(errors=[f"Only {left} left in stock for {item['product']['name']}."]), 409

    # 3. create order + charge the card
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
               (order_id, name, email, address, cart["total"], "PENDING", sync.now()))
    db.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)",
                   [(order_id, i["product"]["id"], i["product"]["name"], i["product"]["price"], i["quantity"])
                    for i in cart["items"]])
    status, errors = charge_card(order_id, cart["total"], data.get("card_number", ""),
                                 str(data.get("expiry", "")).strip(), str(data.get("cvv", "")).strip())
    if status != "SUCCESS":
        db.execute("UPDATE orders SET status = ? WHERE id = ?", ("PAYMENT_FAILED", order_id))
        return jsonify(order_id=order_id,
                       errors=errors or ["Payment declined by bank. Please try another card."]), 402

    db.execute("UPDATE orders SET status = ? WHERE id = ?", ("PAID", order_id))

    # 4. reduce stock in the product service (it then syncs the new stock to all databases)
    for item in cart["items"]:
        try:
            requests.post(f"{PRODUCT_SERVICE_URL}/products/{item['product']['id']}/reduce-stock",
                          json={"quantity": item["quantity"]}, timeout=5)
        except requests.RequestException:
            pass

    # 5. clear the cart
    try:
        requests.delete(f"{CART_SERVICE_URL}/cart/{data['cart_id']}", timeout=5)
    except requests.RequestException:
        pass
    return jsonify(order_id=order_id, status="PAID"), 201


@app.get("/orders")
def list_orders():
    return jsonify(db.query("SELECT * FROM orders ORDER BY created_at DESC"))


@app.get("/orders/<order_id>")
def get_order(order_id):
    order = db.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        return jsonify(error="Order not found"), 404
    order["items"] = db.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    order["payment"] = db.query("SELECT * FROM payments WHERE order_id = ? ORDER BY created_at DESC",
                                (order_id,), one=True)
    return jsonify(order)


init_db()
sync.register_replica_routes(app, "order-service")
sync.start_background_sync(PRODUCT_SERVICE_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
