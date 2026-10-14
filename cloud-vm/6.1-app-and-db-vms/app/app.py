"""
ShopEasy - Task 6.1: application on VM1, database on VM2
---------------------------------------------------------
This is the monolithic ShopEasy app, changed so its database is NOT on the
same machine. It connects to MySQL on VM2 using VM2's INTERNAL IP address
(set with the DB_HOST environment variable, e.g. DB_HOST=10.160.0.3).
"""
import os
import socket
import uuid
from datetime import datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for

import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
PORT = int(os.environ.get("PORT", 5000))

SEED_PRODUCTS = [
    (1, "Wireless Headphones", "Electronics", 2499, "Over-ear Bluetooth headphones with 30-hour battery and deep bass.", "🎧"),
    (2, "Smart Watch", "Electronics", 3999, "Fitness tracking, heart-rate monitor and notifications on your wrist.", "⌚"),
    (3, "Bluetooth Speaker", "Electronics", 1799, "Portable waterproof speaker with 12-hour playtime.", "🔊"),
    (4, "Running Shoes", "Fashion", 2999, "Lightweight cushioned shoes built for daily runs.", "👟"),
    (5, "Denim Jacket", "Fashion", 1999, "Classic blue denim jacket, regular fit.", "🧥"),
    (6, "Backpack", "Accessories", 1299, "25L laptop backpack with padded compartment.", "🎒"),
    (7, "Sunglasses", "Accessories", 899, "UV400 polarised sunglasses.", "🕶️"),
    (8, "Coffee Mug", "Home", 349, "350ml ceramic mug, microwave safe.", "☕"),
    (9, "Desk Lamp", "Home", 1149, "LED desk lamp with 3 brightness levels.", "💡"),
    (10, "Python Programming Book", "Books", 699, "Beginner-friendly guide to Python programming.", "📘"),
]


def init_db():
    """Create tables on the remote database (VM2) if they don't exist, and add sample products."""
    db.execute("""CREATE TABLE IF NOT EXISTS products (
        id INT PRIMARY KEY, name VARCHAR(100) NOT NULL, category VARCHAR(50) NOT NULL,
        price DOUBLE NOT NULL, description VARCHAR(255), icon VARCHAR(16))""")
    db.execute("""CREATE TABLE IF NOT EXISTS orders (
        id VARCHAR(20) PRIMARY KEY, customer_name VARCHAR(100), email VARCHAR(100),
        address VARCHAR(255), total DOUBLE, status VARCHAR(20), created_at VARCHAR(20))""")
    db.execute("""CREATE TABLE IF NOT EXISTS order_items (
        order_id VARCHAR(20), product_id INT, name VARCHAR(100), price DOUBLE, quantity INT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS payments (
        id VARCHAR(20) PRIMARY KEY, order_id VARCHAR(20), amount DOUBLE, method VARCHAR(10),
        card_last4 VARCHAR(4), status VARCHAR(20), created_at VARCHAR(20))""")
    if db.query("SELECT COUNT(*) AS n FROM products", one=True)["n"] == 0:
        db.executemany("INSERT INTO products (id, name, category, price, description, icon) VALUES (?,?,?,?,?,?)",
                       SEED_PRODUCTS)


# ---------------------------------------------------------------- helpers
def get_cart():
    return session.setdefault("cart", {})


def cart_details():
    cart = get_cart()
    if not cart:
        return [], 0
    ids = list(cart.keys())
    rows = db.query(f"SELECT * FROM products WHERE id IN ({','.join('?' * len(ids))})", ids)
    items, total = [], 0
    for p in rows:
        qty = cart[str(p["id"])]
        subtotal = p["price"] * qty
        total += subtotal
        items.append({"product": p, "quantity": qty, "subtotal": subtotal})
    return items, total


@app.context_processor
def inject_globals():
    return {"cart_count": sum(session.get("cart", {}).values()),
            "architecture": f"App VM · DB at {db.DB_HOST}" if db.DB_TYPE == "mysql" else "App VM · local DB"}


# ---------------------------------------------------------------- catalog + search
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sql, params = "SELECT * FROM products WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
        params += [f"%{q}%"] * 3
    if category:
        sql += " AND category = ?"
        params.append(category)
    products = db.query(sql + " ORDER BY id", params)
    categories = [r["category"] for r in db.query("SELECT DISTINCT category FROM products ORDER BY category")]
    return render_template("index.html", products=products, q=q, categories=categories, category=category)


@app.route("/product/<int:pid>")
def product_detail(pid):
    product = db.query("SELECT * FROM products WHERE id = ?", (pid,), one=True)
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("index"))
    return render_template("product.html", product=product)


# ---------------------------------------------------------------- cart
@app.route("/cart")
def view_cart():
    items, total = cart_details()
    return render_template("cart.html", items=items, total=total)


@app.post("/cart/add/<int:pid>")
def add_to_cart(pid):
    qty = max(1, int(request.form.get("quantity", 1)))
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + qty
    session.modified = True
    flash("Added to cart.", "success")
    return redirect(request.referrer or url_for("index"))


@app.post("/cart/update/<int:pid>")
def update_cart(pid):
    qty = int(request.form.get("quantity", 1))
    cart = get_cart()
    if qty <= 0:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = qty
    session.modified = True
    return redirect(url_for("view_cart"))


@app.post("/cart/remove/<int:pid>")
def remove_from_cart(pid):
    get_cart().pop(str(pid), None)
    session.modified = True
    return redirect(url_for("view_cart"))


# ---------------------------------------------------------------- checkout + payment
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = cart_details()
    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template("checkout.html", items=items, total=total)

    f = request.form
    name, email, address = f.get("name", "").strip(), f.get("email", "").strip(), f.get("address", "").strip()
    card = f.get("card_number", "").replace(" ", "")
    expiry, cvv = f.get("expiry", "").strip(), f.get("cvv", "").strip()

    errors = []
    if not (name and email and address):
        errors.append("Please fill in your name, email and address.")
    if not (card.isdigit() and len(card) == 16):
        errors.append("Card number must be 16 digits.")
    if len(expiry) != 5 or expiry[2] != "/":
        errors.append("Expiry must be in MM/YY format.")
    if not (cvv.isdigit() and len(cvv) == 3):
        errors.append("CVV must be 3 digits.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("checkout.html", items=items, total=total, form=f)

    payment_ok = not card.endswith("0000")  # mock gateway: cards ending 0000 are declined
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
               (order_id, name, email, address, total, "PAID" if payment_ok else "PAYMENT_FAILED", now))
    db.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)",
                   [(order_id, i["product"]["id"], i["product"]["name"], i["product"]["price"], i["quantity"])
                    for i in items])
    db.execute("INSERT INTO payments VALUES (?,?,?,?,?,?,?)",
               ("PAY-" + uuid.uuid4().hex[:8].upper(), order_id, total, "CARD", card[-4:],
                "SUCCESS" if payment_ok else "DECLINED", now))

    if not payment_ok:
        flash("Payment declined by bank. Please try another card.", "error")
        return render_template("checkout.html", items=items, total=total, form=f)

    session["cart"] = {}
    return redirect(url_for("order_success", order_id=order_id))


@app.route("/order/<order_id>")
def order_success(order_id):
    order = db.query("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if order is None:
        return redirect(url_for("index"))
    items = db.query("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
    payment = db.query("SELECT * FROM payments WHERE order_id = ?", (order_id,), one=True)
    return render_template("order_success.html", order=order, items=items, payment=payment)


@app.route("/orders")
def orders():
    rows = db.query("SELECT * FROM orders ORDER BY created_at DESC")
    return render_template("orders.html", orders=rows)


# ---------------------------------------------------------------- proof page for the assignment
@app.route("/dbinfo")
def dbinfo():
    """Shows that this app (VM1) talks to the database on VM2 over the internal network."""
    counts = {t: db.query(f"SELECT COUNT(*) AS n FROM {t}", one=True)["n"]
              for t in ("products", "orders", "order_items", "payments")}
    try:
        app_ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        app_ip = "-"
    return render_template("dbinfo.html", info=db.info(), counts=counts,
                           app_host=socket.gethostname(), app_ip=app_ip)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
