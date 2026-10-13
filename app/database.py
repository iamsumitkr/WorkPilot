import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DATABASE_PATH", "workpilot.db")

SAMPLE_INVOICES = [
    ("INV-1040", "ABC Supplies", 18200.00, "2026-10-10", "unpaid", "2026-09-20"),
    ("INV-1042", "ABC Supplies", 24500.00, "2026-10-20", "unpaid", "2026-10-01"),
    ("INV-1043", "ABC Supplies", 9100.00, "2026-10-25", "paid", "2026-10-05"),
    ("INV-2081", "Northwind Components", 37600.00, "2026-10-18", "unpaid", "2026-09-28"),
    ("INV-3007", "Metro Packaging", 12800.00, "2026-11-02", "unpaid", "2026-10-07"),
]

@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db(reset: bool = False) -> None:
    with connection() as conn:
        if reset:
            conn.execute("DROP TABLE IF EXISTS finance_records")
            conn.execute("DROP TABLE IF EXISTS invoices")
        conn.execute("""CREATE TABLE IF NOT EXISTS invoices (
            invoice_id TEXT PRIMARY KEY, company TEXT NOT NULL, amount REAL NOT NULL,
            due_date TEXT NOT NULL, status TEXT NOT NULL, invoice_date TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS finance_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL UNIQUE,
            company TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO invoices VALUES (?, ?, ?, ?, ?, ?)", SAMPLE_INVOICES
            )

def list_invoices():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM invoices ORDER BY invoice_date DESC").fetchall()
        return [dict(row) for row in rows]

def find_invoices(company: str, status: str = "unpaid"):
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE company LIKE ? AND status = ? ORDER BY invoice_date DESC",
            (f"%{company}%", status.lower()),
        ).fetchall()
        return [dict(row) for row in rows]

def create_record(invoice_id: str):
    with connection() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
        if invoice is None:
            return {"ok": False, "error": f"Invoice {invoice_id} does not exist."}
        existing = conn.execute("SELECT * FROM finance_records WHERE invoice_id = ?", (invoice_id,)).fetchone()
        if existing:
            return {"ok": True, "already_exists": True, "record": dict(existing)}
        conn.execute(
            "INSERT INTO finance_records (invoice_id, company, amount, due_date) VALUES (?, ?, ?, ?)",
            (invoice["invoice_id"], invoice["company"], invoice["amount"], invoice["due_date"]),
        )
        row = conn.execute("SELECT * FROM finance_records WHERE invoice_id = ?", (invoice_id,)).fetchone()
        return {"ok": True, "already_exists": False, "record": dict(row)}

def get_record(invoice_id: str):
    with connection() as conn:
        row = conn.execute("SELECT * FROM finance_records WHERE invoice_id = ?", (invoice_id,)).fetchone()
        return dict(row) if row else None

def verify_record(invoice_id: str):
    with connection() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
        record = conn.execute("SELECT * FROM finance_records WHERE invoice_id = ?", (invoice_id,)).fetchone()
        if not invoice or not record:
            return {"verified": False, "reason": "Source invoice or finance record is missing."}
        checks = {
            "invoice_id": invoice["invoice_id"] == record["invoice_id"],
            "company": invoice["company"] == record["company"],
            "amount": abs(float(invoice["amount"]) - float(record["amount"])) < 0.001,
            "due_date": invoice["due_date"] == record["due_date"],
        }
        return {"verified": all(checks.values()), "checks": checks, "record": dict(record)}

def list_records():
    with connection() as conn:
        rows = conn.execute("SELECT * FROM finance_records ORDER BY record_id DESC").fetchall()
        return [dict(row) for row in rows]
