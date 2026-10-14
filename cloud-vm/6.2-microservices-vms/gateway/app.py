"""
Frontend / API Gateway - runs on gateway-vm, the ONLY VM with an EXTERNAL IP.
Serves the web pages on port 80. It has no database of its own: every page is
built from REST calls to the microservices on their INTERNAL IPs.
"""
import os
import uuid

import requests
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001")
CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://localhost:5002")
ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://localhost:5003")
PORT = int(os.environ.get("PORT", 5000))

SERVICES = {
    "product-service": PRODUCT_SERVICE_URL,
    "cart-service": CART_SERVICE_URL,
    "order-service": ORDER_SERVICE_URL,
}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def cart_id():
    if "cart_id" not in session:
        session["cart_id"] = uuid.uuid4().hex
    return session["cart_id"]


def call(method, url, **kwargs):
    """Call a service. Returns (json, status) or (None, 503) if it is unreachable."""
    try:
        r = requests.request(method, url, timeout=5, **kwargs)
        return r.json(), r.status_code
    except (requests.RequestException, ValueError):
        return None, 503


def require(data, status, service):
    if status == 503:
        abort(503, description=f"{service} is not reachable. Is it running?")
    return data


@app.context_processor
def inject_globals():
    data, status = call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}")
    return {"cart_count": data["count"] if status == 200 else 0, "architecture": "Microservices on VMs"}


@app.errorhandler(503)
def service_down(e):
    return render_template("error.html", message=str(e.description)), 503


# ---------------------------------------------------------------- shop pages
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    products = require(*call("GET", f"{PRODUCT_SERVICE_URL}/products",
                             params={"q": q, "category": category}), "Product service")
    categories = require(*call("GET", f"{PRODUCT_SERVICE_URL}/categories"), "Product service")
    return render_template("index.html", products=products, q=q, categories=categories, category=category)


@app.route("/product/<int:pid>")
def product_detail(pid):
    product, status = call("GET", f"{PRODUCT_SERVICE_URL}/products/{pid}")
    require(product, status, "Product service")
    if status != 200:
        flash("Product not found.", "error")
        return redirect(url_for("index"))
    return render_template("product.html", product=product)


@app.route("/cart")
def view_cart():
    cart = require(*call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}"), "Cart service")
    return render_template("cart.html", items=cart["items"], total=cart["total"])


@app.post("/cart/add/<int:pid>")
def add_to_cart(pid):
    qty = max(1, int(request.form.get("quantity", 1)))
    data, status = call("POST", f"{CART_SERVICE_URL}/cart/{cart_id()}/items", json={"product_id": pid, "quantity": qty})
    require(data, status, "Cart service")
    if status == 201:
        flash("Added to cart.", "success")
    else:
        flash(data.get("error", "Could not add to cart."), "error")
    return redirect(request.referrer or url_for("index"))


@app.post("/cart/update/<int:pid>")
def update_cart(pid):
    data, status = call("PUT", f"{CART_SERVICE_URL}/cart/{cart_id()}/items/{pid}",
                        json={"quantity": int(request.form.get("quantity", 1))})
    require(data, status, "Cart service")
    if status != 200:
        flash(data.get("error", "Could not update cart."), "error")
    return redirect(url_for("view_cart"))


@app.post("/cart/remove/<int:pid>")
def remove_from_cart(pid):
    require(*call("DELETE", f"{CART_SERVICE_URL}/cart/{cart_id()}/items/{pid}"), "Cart service")
    return redirect(url_for("view_cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = require(*call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}"), "Cart service")
    if not cart["items"]:
        flash("Your cart is empty.", "error")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template("checkout.html", items=cart["items"], total=cart["total"])

    payload = {k: request.form.get(k, "") for k in ("name", "email", "address", "card_number", "expiry", "cvv")}
    payload["cart_id"] = cart_id()
    result, status = call("POST", f"{ORDER_SERVICE_URL}/orders", json=payload)
    require(result, status, "Order service")
    if status != 201:
        for e in result.get("errors", ["Something went wrong."]):
            flash(e, "error")
        return render_template("checkout.html", items=cart["items"], total=cart["total"], form=request.form)
    return redirect(url_for("order_success", order_id=result["order_id"]))


@app.route("/order/<order_id>")
def order_success(order_id):
    order, status = call("GET", f"{ORDER_SERVICE_URL}/orders/{order_id}")
    require(order, status, "Order service")
    if status != 200:
        return redirect(url_for("index"))
    return render_template("order_success.html", order=order, items=order["items"], payment=order["payment"])


@app.route("/orders")
def orders():
    return render_template("orders.html", orders=require(*call("GET", f"{ORDER_SERVICE_URL}/orders"), "Order service"))


# ---------------------------------------------------------------- assignment proof pages
@app.route("/services")
def services():
    rows = []
    for name, url in SERVICES.items():
        data, status = call("GET", f"{url}/health")
        rows.append({"name": name, "url": url, "up": status == 200,
                     "host": data.get("host") if data else "-", "database": data.get("database") if data else "-"})
    return render_template("services.html", services=rows)


@app.route("/sync")
def sync_status():
    """Compare the product data held in each service's own database."""
    dbs = []
    for name, url in SERVICES.items():
        data, status = call("GET", f"{url}/sync/status")
        dbs.append({"name": name, "ok": status == 200, "data": data or {}})
    checksums = {d["data"].get("checksum") for d in dbs if d["ok"]}
    in_sync = all(d["ok"] for d in dbs) and len(checksums) == 1
    # one row per product, one price/stock column per database
    by_db = {d["name"]: {p["id"]: p for p in d["data"].get("products", [])} for d in dbs}
    master = by_db.get("product-service", {})
    rows = []
    for pid, p in sorted(master.items()):
        cells = [by_db[d["name"]].get(pid) for d in dbs]
        same = all(c and c["price"] == p["price"] and c["stock"] == p["stock"] for c in cells)
        rows.append({"id": pid, "name": p["name"], "cells": cells, "same": same})
    return render_template("sync.html", dbs=dbs, in_sync=in_sync, rows=rows)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    """Change a product's price/stock in the product service; it syncs to the other databases."""
    if request.method == "POST":
        pid = int(request.form["id"])
        data, status = call("PUT", f"{PRODUCT_SERVICE_URL}/products/{pid}",
                            json={"price": float(request.form["price"]), "stock": int(request.form["stock"])})
        require(data, status, "Product service")
        flash(f"Updated {data['name']} in productdb. The change was pushed to cartdb and orderdb.", "success")
        return redirect(url_for("admin"))
    products = require(*call("GET", f"{PRODUCT_SERVICE_URL}/products"), "Product service")
    return render_template("admin.html", products=products)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
