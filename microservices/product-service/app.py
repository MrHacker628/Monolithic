"""
Product Service (port 5001)
Owns the product catalogue and search. Has its own database: products.db
"""
import os
import sqlite3

from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "products.db")
PORT = int(os.environ.get("PORT", 5001))

app = Flask(__name__)

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


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
        price REAL NOT NULL, description TEXT, icon TEXT)""")
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany("INSERT INTO products (name, category, price, description, icon) VALUES (?,?,?,?,?)",
                         SEED_PRODUCTS)
    conn.commit()
    conn.close()


@app.get("/")
def home():
    """This is an API service, not a web page. Open the shop at http://localhost:5000"""
    return jsonify(service="product-service", message="This is a REST API. Open the shop at http://localhost:5000",
                   endpoints=["GET /products?q=&category=", "GET /products/<id>", "GET /categories", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="product-service", status="UP")


@app.get("/products")
def list_products():
    """List products. Supports ?q=<search text>, ?category=<name> and ?ids=1,2,3"""
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    ids = request.args.get("ids", "").strip()
    sql, params = "SELECT * FROM products WHERE 1=1", []
    if q:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
        params += [f"%{q}%"] * 3
    if category:
        sql += " AND category = ?"
        params.append(category)
    if ids:
        id_list = [i for i in ids.split(",") if i.isdigit()]
        if not id_list:
            return jsonify([])
        sql += f" AND id IN ({','.join('?' * len(id_list))})"
        params += id_list
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/products/<int:pid>")
def get_product(pid):
    with db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if row is None:
        return jsonify(error="Product not found"), 404
    return jsonify(dict(row))


@app.get("/categories")
def categories():
    with db() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return jsonify([r[0] for r in rows])


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
