"""SQLite storage for the simulated company systems (mail, ERP, vendor portal, helpdesk)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from config import SANDBOX_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    folder TEXT NOT NULL DEFAULT 'inbox',      -- inbox | sent | drafts
    sender_name TEXT NOT NULL,
    sender_email TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    attachment TEXT,                            -- filename under ATTACHMENTS_DIR
    received_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY,
    vendor TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    due_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',        -- open | paid
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'seed',
    UNIQUE(vendor, invoice_number)
);
CREATE TABLE IF NOT EXISTS portal_invoices (
    id INTEGER PRIMARY KEY,
    invoice_number TEXT UNIQUE NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    pdf TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    requester TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',        -- open | closed
    priority TEXT NOT NULL DEFAULT 'normal'
);
CREATE TABLE IF NOT EXISTS ticket_notes (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SANDBOX_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with session() as c:
        c.executescript(SCHEMA)


def rows(conn: sqlite3.Connection, sql: str, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_setting(key: str, default: str = "") -> str:
    with session() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    with session() as c:
        c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def dump_state() -> dict:
    """Full ground-truth snapshot, used by eval checkers and tests (never shown to the agent)."""
    with session() as c:
        return {
            "emails": rows(c, "SELECT * FROM emails ORDER BY id"),
            "bills": rows(c, "SELECT * FROM bills ORDER BY id"),
            "vendors": rows(c, "SELECT * FROM vendors ORDER BY id"),
            "portal_invoices": rows(c, "SELECT * FROM portal_invoices ORDER BY id"),
            "tickets": rows(c, "SELECT * FROM tickets ORDER BY id"),
            "ticket_notes": rows(c, "SELECT * FROM ticket_notes ORDER BY id"),
        }
