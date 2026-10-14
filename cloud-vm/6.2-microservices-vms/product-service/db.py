"""
Tiny database helper used by every app in this folder.

On the VMs we use MySQL (DB_TYPE=mysql). For quick local testing on a laptop
you can use SQLite instead (DB_TYPE=sqlite, the default) - no MySQL needed.
All SQL in the apps is written so it works on both.

Environment variables:
  DB_TYPE      mysql | sqlite        (default: sqlite)
  DB_HOST      MySQL host / IP       (default: 127.0.0.1)
  DB_PORT      MySQL port            (default: 3306)
  DB_USER      MySQL user            (default: shopeasy)
  DB_PASSWORD  MySQL password
  DB_NAME      MySQL database name / SQLite file name
"""
import os
import sqlite3

DB_TYPE = os.environ.get("DB_TYPE", "sqlite").lower()
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "shopeasy")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "shopeasy")

if DB_TYPE == "mysql":
    import pymysql
    import pymysql.cursors


def _connect():
    if DB_TYPE == "mysql":
        return pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
                               database=DB_NAME, charset="utf8mb4", autocommit=True,
                               cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)
    path = DB_NAME if DB_NAME.endswith(".db") else DB_NAME + ".db"
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _sql(sql):
    # Apps write "?" placeholders; MySQL (PyMySQL) uses "%s"
    return sql.replace("?", "%s") if DB_TYPE == "mysql" else sql


def query(sql, params=(), one=False):
    """Run a SELECT. Returns a list of dicts (or one dict / None if one=True)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), tuple(params))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=()):
    """Run one INSERT / UPDATE / DELETE / CREATE statement."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), tuple(params))
        conn.commit()
    finally:
        conn.close()


def executemany(sql, seq_of_params):
    seq = [tuple(p) for p in seq_of_params]
    if not seq:
        return
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.executemany(_sql(sql), seq)
        conn.commit()
    finally:
        conn.close()


def info():
    """Describe where the database is (shown on the app's DB info page)."""
    if DB_TYPE == "mysql":
        version = query("SELECT VERSION() AS v", one=True)["v"]
        return {"type": "MySQL", "host": DB_HOST, "port": DB_PORT, "database": DB_NAME, "version": version}
    return {"type": "SQLite (local test mode)", "host": "local file", "port": "-",
            "database": DB_NAME, "version": sqlite3.sqlite_version}
