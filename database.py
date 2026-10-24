"""
database.py
===========
MySQL access layer. Every query uses %s placeholders with a parameter tuple
(parameterised queries), which protects the app from SQL injection.
Credentials are read from the .env file - nothing is hard-coded.
"""

import os
from decimal import Decimal

import mysql.connector
from mysql.connector import Error as MySQLError, pooling
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

_pool = None


def _get_pool():
    """Create the connection pool the first time it is needed."""
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="scholarship_pool",
            pool_size=5,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "smart_scholarship"),
            charset="utf8mb4",
            autocommit=True,   # each statement is committed immediately
        )
    return _pool


def _clean(row):
    """MySQL DECIMAL values arrive as Decimal; convert to float for templates/JSON."""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


def fetch_all(sql, params=None):
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return [_clean(r) for r in rows]
    finally:
        conn.close()          # returns the connection to the pool


def fetch_one(sql, params=None):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """Run INSERT / UPDATE / DELETE. Returns (last_insert_id, affected_rows)."""
    conn = _get_pool().get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        result = (cur.lastrowid, cur.rowcount)
        cur.close()
        return result
    finally:
        conn.close()


def init_admin():
    """
    Create (or refresh) the admin account from ADMIN_USERNAME / ADMIN_PASSWORD
    in .env. Only a password hash is stored in MySQL.
    """
    username = (os.getenv("ADMIN_USERNAME") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not username or not password:
        print("[warning] ADMIN_USERNAME / ADMIN_PASSWORD missing in .env - admin login disabled.")
        return
    existing = fetch_one("SELECT admin_id, password_hash FROM admin WHERE username=%s", (username,))
    if existing is None:
        execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s)",
                (username, generate_password_hash(password)))
        print(f"[info] Admin account '{username}' created from .env")
    elif not check_password_hash(existing["password_hash"], password):
        execute("UPDATE admin SET password_hash=%s WHERE admin_id=%s",
                (generate_password_hash(password), existing["admin_id"]))
        print(f"[info] Admin password for '{username}' updated from .env")
