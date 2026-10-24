"""
Product Service (port 5001)
Serves the product catalogue + search, and the shop's web page at "/".
Every response says which VM ("served_by") handled it, so you can see the
load balancer spreading requests across the Managed Instance Group.
"""
import os
import socket

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")
HOST = socket.gethostname()

PRODUCTS = [
    {"id": 1, "name": "Wireless Headphones", "category": "Electronics", "price": 2499, "icon": "🎧"},
    {"id": 2, "name": "Smart Watch", "category": "Electronics", "price": 3999, "icon": "⌚"},
    {"id": 3, "name": "Bluetooth Speaker", "category": "Electronics", "price": 1799, "icon": "🔊"},
    {"id": 4, "name": "Running Shoes", "category": "Fashion", "price": 2999, "icon": "👟"},
    {"id": 5, "name": "Denim Jacket", "category": "Fashion", "price": 1999, "icon": "🧥"},
    {"id": 6, "name": "Backpack", "category": "Accessories", "price": 1299, "icon": "🎒"},
    {"id": 7, "name": "Sunglasses", "category": "Accessories", "price": 899, "icon": "🕶️"},
    {"id": 8, "name": "Coffee Mug", "category": "Home", "price": 349, "icon": "☕"},
    {"id": 9, "name": "Desk Lamp", "category": "Home", "price": 1149, "icon": "💡"},
    {"id": 10, "name": "Python Programming Book", "category": "Books", "price": 699, "icon": "📘"},
]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    return jsonify(service="product-service", status="UP", served_by=HOST)


@app.get("/products")
def list_products():
    q = request.args.get("q", "").strip().lower()
    items = [p for p in PRODUCTS if q in p["name"].lower() or q in p["category"].lower()] if q else PRODUCTS
    return jsonify(service="product-service", served_by=HOST, count=len(items), products=items)


@app.get("/products/<int:pid>")
def get_product(pid):
    for p in PRODUCTS:
        if p["id"] == pid:
            return jsonify(service="product-service", served_by=HOST, product=p)
    return jsonify(error="Product not found", served_by=HOST), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
