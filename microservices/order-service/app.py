"""
Order Service (port 5003)
Owns orders. Has its own database: orders.db
To place an order it talks to three other services over HTTP:
  Cart Service    -> get the items in the cart
  Payment Service -> charge the card
  Cart Service    -> clear the cart after a successful payment
"""
import os
import sqlite3
import uuid
from datetime import datetime

import requests
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "orders.db")
PORT = int(os.environ.get("PORT", 5003))
CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://localhost:5002")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:5004")

app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, customer_name TEXT, email TEXT, address TEXT,
                total REAL, status TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS order_items (
                order_id TEXT, product_id INTEGER, name TEXT, price REAL, quantity INTEGER);
        """)


def set_status(order_id, status):
    with db() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


@app.get("/")
def home():
    """This is an API service, not a web page. Open the shop at http://localhost:5000"""
    return jsonify(service="order-service", message="This is a REST API. Open the shop at http://localhost:5000",
                   endpoints=["POST /orders", "GET /orders", "GET /orders/<order_id>", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="order-service", status="UP")


@app.post("/orders")
def place_order():
    data = request.get_json(force=True)
    name, email, address = (data.get(k, "").strip() for k in ("name", "email", "address"))
    if not (name and email and address):
        return jsonify(errors=["Please fill in your name, email and address."]), 400

    # 1. Get cart contents from the Cart Service
    cart = requests.get(f"{CART_SERVICE_URL}/cart/{data['cart_id']}", timeout=5).json()
    if not cart["items"]:
        return jsonify(errors=["Your cart is empty."]), 400

    # 2. Create the order as PENDING
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    with db() as conn:
        conn.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
                     (order_id, name, email, address, cart["total"], "PENDING",
                      datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)",
                         [(order_id, i["product"]["id"], i["product"]["name"],
                           i["product"]["price"], i["quantity"]) for i in cart["items"]])

    # 3. Ask the Payment Service to charge the card
    pay = requests.post(f"{PAYMENT_SERVICE_URL}/payments", timeout=5, json={
        "order_id": order_id, "amount": cart["total"], "card_number": data.get("card_number", ""),
        "expiry": data.get("expiry", ""), "cvv": data.get("cvv", "")})
    payment = pay.json()

    if payment.get("status") == "INVALID":
        set_status(order_id, "PAYMENT_FAILED")
        return jsonify(order_id=order_id, errors=payment["errors"]), 400
    if payment.get("status") != "SUCCESS":
        set_status(order_id, "PAYMENT_FAILED")
        return jsonify(order_id=order_id, errors=["Payment declined by bank. Please try another card."]), 402

    # 4. Payment OK: mark order PAID and clear the cart
    set_status(order_id, "PAID")
    requests.delete(f"{CART_SERVICE_URL}/cart/{data['cart_id']}", timeout=5)
    return jsonify(order_id=order_id, status="PAID", payment=payment), 201


@app.get("/orders")
def list_orders():
    with db() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/orders/<order_id>")
def get_order(order_id):
    with db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            return jsonify(error="Order not found"), 404
        items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    result = dict(order)
    result["items"] = [dict(i) for i in items]
    return jsonify(result)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
