"""
Order Service (port 5003)
POST /orders  {"name": "...", "items": [...], "card_number": "4242 4242 4242 4242"}
1. asks the cart service (same VM) to price the cart
2. runs the mock payment gateway (test mode) and signs the payment
3. returns the order confirmation

Payment signing is deliberately CPU-heavy, so placing orders under load
pushes the VMs' CPU up and makes the autoscaler add instances.
"""
import hashlib
import os
import socket
import uuid
from datetime import datetime

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
HOST = socket.gethostname()
CART_URL = os.environ.get("CART_URL", "http://127.0.0.1:5002")
WORK = int(os.environ.get("ORDER_WORK", 80000))  # CPU work per payment signature
orders_served = 0


def sign_payment(order_id, amount, card_last4):
    payload = f"{order_id}|{amount}|{card_last4}".encode()
    return hashlib.pbkdf2_hmac("sha256", payload, b"shopeasy-payments", WORK).hex()[:16]


@app.get("/health")
def health():
    return jsonify(service="order-service", status="UP", served_by=HOST)


@app.get("/orders")
def info():
    return jsonify(service="order-service", served_by=HOST, orders_served_by_this_vm=orders_served)


@app.post("/orders")
def place_order():
    global orders_served
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip() or "Guest"
    card = str(data.get("card_number", "")).replace(" ", "")
    if not (card.isdigit() and len(card) == 16):
        return jsonify(error="Card number must be 16 digits.", served_by=HOST), 400

    try:
        cart = requests.post(f"{CART_URL}/cart/quote", json={"items": data.get("items", [])}, timeout=10)
    except requests.RequestException:
        return jsonify(error="Cart service unavailable", served_by=HOST), 503
    if cart.status_code != 200:
        return jsonify(error=cart.json().get("error", "Cart error"), served_by=HOST), 400
    quote = cart.json()

    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    if card.endswith("0000"):
        return jsonify(order_id=order_id, status="PAYMENT_DECLINED", served_by=HOST,
                       error="Payment declined by bank (test card ending 0000)."), 402

    signature = sign_payment(order_id, quote["total"], card[-4:])
    orders_served += 1
    return jsonify(service="order-service", served_by=HOST, cart_priced_by=quote["served_by"],
                   order_id=order_id, status="PAID", customer=name, total=quote["total"],
                   payment={"id": "PAY-" + uuid.uuid4().hex[:8].upper(), "card_last4": card[-4:],
                            "signature": signature},
                   created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5003)))
