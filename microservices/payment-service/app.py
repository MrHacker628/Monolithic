"""
Payment Service (port 5004)
Mock payment gateway (test mode - no real money). Has its own database: payments.db
Any valid 16-digit card is approved; a card ending in 0000 is declined (for demo).
"""
import os
import sqlite3
import uuid
from datetime import datetime

from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "payments.db")
PORT = int(os.environ.get("PORT", 5004))

app = Flask(__name__)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY, order_id TEXT, amount REAL, method TEXT,
            card_last4 TEXT, status TEXT, created_at TEXT)""")


@app.get("/")
def home():
    """This is an API service, not a web page. Open the shop at http://localhost:5000"""
    return jsonify(service="payment-service", message="This is a REST API. Open the shop at http://localhost:5000",
                   endpoints=["POST /payments", "GET /payments/<order_id>", "GET /health"])


@app.get("/health")
def health():
    return jsonify(service="payment-service", status="UP")


@app.post("/payments")
def make_payment():
    data = request.get_json(force=True)
    card = str(data.get("card_number", "")).replace(" ", "")
    expiry, cvv = str(data.get("expiry", "")).strip(), str(data.get("cvv", "")).strip()

    errors = []
    if not (card.isdigit() and len(card) == 16):
        errors.append("Card number must be 16 digits.")
    if len(expiry) != 5 or expiry[2] != "/":
        errors.append("Expiry must be in MM/YY format.")
    if not (cvv.isdigit() and len(cvv) == 3):
        errors.append("CVV must be 3 digits.")
    if errors:
        return jsonify(status="INVALID", errors=errors), 400

    status = "DECLINED" if card.endswith("0000") else "SUCCESS"
    payment = {
        "id": "PAY-" + uuid.uuid4().hex[:8].upper(),
        "order_id": data["order_id"],
        "amount": float(data["amount"]),
        "method": "CARD",
        "card_last4": card[-4:],
        "status": status,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with db() as conn:
        conn.execute("INSERT INTO payments VALUES (:id,:order_id,:amount,:method,:card_last4,:status,:created_at)",
                     payment)
    return jsonify(payment), (201 if status == "SUCCESS" else 402)


@app.get("/payments/<order_id>")
def get_payment(order_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM payments WHERE order_id = ? ORDER BY created_at DESC",
                           (order_id,)).fetchone()
    if row is None:
        return jsonify(error="Payment not found"), 404
    return jsonify(dict(row))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
