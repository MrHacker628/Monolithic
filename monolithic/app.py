"""
ShopEasy - Monolithic E-commerce Application
--------------------------------------------
Everything (product catalog, search, cart, orders, payment) lives in ONE
Flask application, shares ONE SQLite database, and runs as ONE process.
"""
import os
import sqlite3
import uuid
from datetime import datetime

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shop.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

SEED_PRODUCTS = [
    ("Wireless Headphones", "Electronics", 2499, "Over-ear Bluetooth headphones with 30-hour battery and deep bass.", "🎧"),
    ("Smart Watch", "Electronics", 3999, "Fitness tracking, heart-rate monitor and notifications on your wrist.", "⌚"),
    ("Bluetooth Speaker", "Electronics", 1799, "Portable waterproof speaker with 12-hour playtime.", "🔊"),
    ("Running Shoes", "Fashion", 2999, "Lightweight cushioned shoes built for daily runs.", "👟"),
    ("Denim Jacket", "Fashion", 1999, "Classic blue denim jacket, regular fit.", "🧥"),
    ("Backpack", "Accessories", 1299, "25L laptop backpack with padded compartment.", "🎒"),
    ("Sunglasses", "Accessories", 899, "UV400 polarised sunglasses.", "🕶️"),
    ("Coffee Mug", "Home", 349, "350ml ceramic mug, microwave safe.", "☕"),
    ("Desk Lamp", "Home", 1149, "LED desk lamp with 3 brightness levels.", "💡"),
    ("Python Programming Book", "Books", 699, "Beginner-friendly guide to Python programming.", "📘"),
]


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL,
            description TEXT, icon TEXT);
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, customer_name TEXT, email TEXT, address TEXT,
            total REAL, status TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS order_items (
            order_id TEXT, product_id INTEGER, name TEXT, price REAL, quantity INTEGER);
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY, order_id TEXT, amount REAL, method TEXT,
            card_last4 TEXT, status TEXT, created_at TEXT);
        """
    )
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO products (name, category, price, description, icon) VALUES (?,?,?,?,?)",
            SEED_PRODUCTS,
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------- helpers
def get_cart():
    return session.setdefault("cart", {})


def cart_details():
    cart = get_cart()
    if not cart:
        return [], 0
    ids = list(cart.keys())
    rows = get_db().execute(
        f"SELECT * FROM products WHERE id IN ({','.join('?' * len(ids))})", ids
    ).fetchall()
    items, total = [], 0
    for p in rows:
        qty = cart[str(p["id"])]
        subtotal = p["price"] * qty
        total += subtotal
        items.append({"product": p, "quantity": qty, "subtotal": subtotal})
    return items, total


@app.context_processor
def inject_cart_count():
    return {"cart_count": sum(session.get("cart", {}).values()),
            "architecture": "Monolithic"}


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
    db = get_db()
    products = db.execute(sql, params).fetchall()
    categories = [r[0] for r in db.execute("SELECT DISTINCT category FROM products ORDER BY category")]
    return render_template("index.html", products=products, q=q,
                           categories=categories, category=category)


@app.route("/product/<int:pid>")
def product_detail(pid):
    product = get_db().execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
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

    # Mock payment gateway: cards ending in 0000 are declined (for demo).
    payment_ok = not card.endswith("0000")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
    db = get_db()
    db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
               (order_id, name, email, address, total,
                "PAID" if payment_ok else "PAYMENT_FAILED", now))
    db.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)",
                   [(order_id, i["product"]["id"], i["product"]["name"],
                     i["product"]["price"], i["quantity"]) for i in items])
    db.execute("INSERT INTO payments VALUES (?,?,?,?,?,?,?)",
               ("PAY-" + uuid.uuid4().hex[:8].upper(), order_id, total, "CARD",
                card[-4:], "SUCCESS" if payment_ok else "DECLINED", now))
    db.commit()

    if not payment_ok:
        flash("Payment declined by bank. Please try another card.", "error")
        return render_template("checkout.html", items=items, total=total, form=f)

    session["cart"] = {}
    return redirect(url_for("order_success", order_id=order_id))


@app.route("/order/<order_id>")
def order_success(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        return redirect(url_for("index"))
    items = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    payment = db.execute("SELECT * FROM payments WHERE order_id = ?", (order_id,)).fetchone()
    return render_template("order_success.html", order=order, items=items, payment=payment)


@app.route("/orders")
def orders():
    rows = get_db().execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return render_template("orders.html", orders=rows)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
