import os
from app import database

def setup_function():
    os.environ["DATABASE_PATH"] = ":memory:"
    # database.DB_PATH is resolved at import, so use a temporary file for tests.
    database.DB_PATH = "test_workpilot.db"
    database.init_db(reset=True)

def teardown_function():
    if os.path.exists("test_workpilot.db"):
        os.remove("test_workpilot.db")

def test_search_returns_newest_first():
    rows = database.find_invoices("ABC Supplies", "unpaid")
    assert rows[0]["invoice_id"] == "INV-1042"
    assert len(rows) == 2

def test_record_creation_and_verification():
    created = database.create_record("INV-1042")
    assert created["ok"] is True
    verified = database.verify_record("INV-1042")
    assert verified["verified"] is True

def test_duplicate_creation_is_idempotent():
    first = database.create_record("INV-1042")
    second = database.create_record("INV-1042")
    assert first["already_exists"] is False
    assert second["already_exists"] is True
    assert len(database.list_records()) == 1

def test_unknown_invoice_is_rejected():
    result = database.create_record("NOT-REAL")
    assert result["ok"] is False
