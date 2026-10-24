"""
setup_database.py  -  one-command database setup (works on Windows, macOS, Linux)

Usage:   python setup_database.py

Reads the MySQL details from .env and runs database/schema.sql for you, so you do
not need the `mysql` command on your PATH. Safe to run more than once.
"""
import os
import sys

import mysql.connector
from dotenv import load_dotenv

load_dotenv()
BASE = os.path.dirname(os.path.abspath(__file__))


def split_statements(sql_text):
    """Remove -- comment lines and split the script into single SQL statements."""
    lines = [ln for ln in sql_text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main():
    with open(os.path.join(BASE, "database", "schema.sql"), encoding="utf-8") as fh:
        statements = split_statements(fh.read())
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
        )
    except mysql.connector.Error as exc:
        print(f"Could not connect to MySQL: {exc}")
        print("Check that MySQL is running and DB_HOST / DB_USER / DB_PASSWORD in .env are correct.")
        sys.exit(1)
    cur = conn.cursor()
    for stmt in statements:
        cur.execute(stmt)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Ran {len(statements)} statements. Database is ready - now run: python app.py")


if __name__ == "__main__":
    main()
