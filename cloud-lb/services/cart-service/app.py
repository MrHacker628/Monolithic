"""
Cart Service (port 5002)
POST /cart/quote  {"items": [{"product_id": 1, "quantity": 2}, ...]}
Prices the cart: gets product prices from the product service (on the same VM),
adds 18% GST and shipping, and runs a pricing/discount calculation.

The cart is kept in the browser and sent with each request, so the service is
STATELESS: any VM in the instance group can answer any request. That is what
lets the load balancer send requests anywhere and the group scale freely.
"""
import hashlib
import os
import socket

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
HOST = socket.gethostname()
PRODUCT_URL = os.environ.get("PRODUCT_URL", "http://127.0.0.1:5001")
# CPU work per quote (simulates a pricing / discount engine). Higher = more CPU per request.
WORK = int(os.environ.get("CART_WORK", 30000))


def pricing_engine(items):
    seed = "|".join(f"{i['product_id']}x{i['quantity']}" for i in items).encode()
    digest = hashlib.pbkdf2_hmac("sha256", seed, b"shopeasy-pricing", WORK)
    return int.from_bytes(digest[:2], "big") % 5  # 0-4 % loyalty discount


@app.get("/health")
def health():
    return jsonify(service="cart-service", status="UP", served_by=HOST)


@app.get("/cart")
def info():
    return jsonify(service="cart-service", served_by=HOST,
                   usage='POST /cart/quote {"items":[{"product_id":1,"quantity":2}]}')


@app.post("/cart/quote")
def quote():
    items = (request.get_json(silent=True) or {}).get("items", [])
    items = [{"product_id": int(i["product_id"]), "quantity": max(1, int(i.get("quantity", 1)))} for i in items]
    if not items:
        return jsonify(error="Cart is empty", served_by=HOST), 400
    catalogue = {p["id"]: p for p in requests.get(f"{PRODUCT_URL}/products", timeout=5).json()["products"]}
    lines, subtotal = [], 0
    for i in items:
        p = catalogue.get(i["product_id"])
        if not p:
            return jsonify(error=f"Unknown product {i['product_id']}", served_by=HOST), 400
        line = p["price"] * i["quantity"]
        subtotal += line
        lines.append({"product_id": p["id"], "name": p["name"], "icon": p["icon"], "price": p["price"],
                      "quantity": i["quantity"], "line_total": line})
    discount_pct = pricing_engine(items)
    discount = round(subtotal * discount_pct / 100, 2)
    gst = round((subtotal - discount) * 0.18, 2)
    shipping = 0 if subtotal >= 2000 else 99
    total = round(subtotal - discount + gst + shipping, 2)
    return jsonify(service="cart-service", served_by=HOST, lines=lines, subtotal=subtotal,
                   discount_pct=discount_pct, discount=discount, gst=gst, shipping=shipping, total=total)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)))
