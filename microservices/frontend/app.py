"""
Frontend / API Gateway (port 5000)
Serves the web pages. Has NO database and NO business logic of its own:
every piece of data comes from a microservice over HTTP (REST).
"""
import os
import uuid

import requests
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001")
CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://localhost:5002")
ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://localhost:5003")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:5004")
PORT = int(os.environ.get("PORT", 5000))

SERVICES = {
    "product-service": PRODUCT_SERVICE_URL,
    "cart-service": CART_SERVICE_URL,
    "order-service": ORDER_SERVICE_URL,
    "payment-service": PAYMENT_SERVICE_URL,
}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def cart_id():
    """Each browser session gets its own cart ID, stored in the Cart Service."""
    if "cart_id" not in session:
        session["cart_id"] = uuid.uuid4().hex
    return session["cart_id"]


def call(method, url, **kwargs):
    """Call a service. Returns (json, status) or (None, 503) if it is down."""
    try:
        r = requests.request(method, url, timeout=5, **kwargs)
        return r.json(), r.status_code
    except requests.RequestException:
        return None, 503


@app.context_processor
def inject_cart_count():
    data, status = call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}")
    return {"cart_count": data["count"] if status == 200 else 0,
            "architecture": "Microservices"}


@app.errorhandler(503)
def service_down(e):
    return render_template("error.html", message=str(e.description)), 503


def require(data, status, service):
    if status == 503:
        abort(503, description=f"{service} is not reachable. Is it running?")
    return data


# ---------------------------------------------------------------- catalog + search -> Product Service
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    products = require(*call("GET", f"{PRODUCT_SERVICE_URL}/products",
                             params={"q": q, "category": category}), "Product Service")
    categories = require(*call("GET", f"{PRODUCT_SERVICE_URL}/categories"), "Product Service")
    return render_template("index.html", products=products, q=q,
                           categories=categories, category=category)


@app.route("/product/<int:pid>")
def product_detail(pid):
    product, status = call("GET", f"{PRODUCT_SERVICE_URL}/products/{pid}")
    require(product, status, "Product Service")
    if status != 200:
        flash("Product not found.", "error")
        return redirect(url_for("index"))
    return render_template("product.html", product=product)


# ---------------------------------------------------------------- cart -> Cart Service
@app.route("/cart")
def view_cart():
    cart = require(*call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}"), "Cart Service")
    return render_template("cart.html", items=cart["items"], total=cart["total"])


@app.post("/cart/add/<int:pid>")
def add_to_cart(pid):
    qty = max(1, int(request.form.get("quantity", 1)))
    require(*call("POST", f"{CART_SERVICE_URL}/cart/{cart_id()}/items",
                  json={"product_id": pid, "quantity": qty}), "Cart Service")
    flash("Added to cart.", "success")
    return redirect(request.referrer or url_for("index"))


@app.post("/cart/update/<int:pid>")
def update_cart(pid):
    require(*call("PUT", f"{CART_SERVICE_URL}/cart/{cart_id()}/items/{pid}",
                  json={"quantity": int(request.form.get("quantity", 1))}), "Cart Service")
    return redirect(url_for("view_cart"))


@app.post("/cart/remove/<int:pid>")
def remove_from_cart(pid):
    require(*call("DELETE", f"{CART_SERVICE_URL}/cart/{cart_id()}/items/{pid}"), "Cart Service")
    return redirect(url_for("view_cart"))


# ---------------------------------------------------------------- checkout -> Order Service (-> Payment Service)
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = require(*call("GET", f"{CART_SERVICE_URL}/cart/{cart_id()}"), "Cart Service")
    if not cart["items"]:
        flash("Your cart is empty.", "error")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template("checkout.html", items=cart["items"], total=cart["total"])

    payload = {k: request.form.get(k, "") for k in ("name", "email", "address", "card_number", "expiry", "cvv")}
    payload["cart_id"] = cart_id()
    result, status = call("POST", f"{ORDER_SERVICE_URL}/orders", json=payload)
    require(result, status, "Order Service")
    if status != 201:
        for e in result.get("errors", ["Something went wrong."]):
            flash(e, "error")
        return render_template("checkout.html", items=cart["items"], total=cart["total"], form=request.form)
    return redirect(url_for("order_success", order_id=result["order_id"]))


@app.route("/order/<order_id>")
def order_success(order_id):
    order, status = call("GET", f"{ORDER_SERVICE_URL}/orders/{order_id}")
    require(order, status, "Order Service")
    if status != 200:
        return redirect(url_for("index"))
    payment = require(*call("GET", f"{PAYMENT_SERVICE_URL}/payments/{order_id}"), "Payment Service")
    return render_template("order_success.html", order=order, items=order["items"], payment=payment)


@app.route("/orders")
def orders():
    rows = require(*call("GET", f"{ORDER_SERVICE_URL}/orders"), "Order Service")
    return render_template("orders.html", orders=rows)


# ---------------------------------------------------------------- service health dashboard
@app.route("/services")
def services():
    statuses = []
    for name, url in SERVICES.items():
        data, status = call("GET", f"{url}/health")
        statuses.append({"name": name, "url": url, "up": status == 200})
    return render_template("services.html", services=statuses)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
