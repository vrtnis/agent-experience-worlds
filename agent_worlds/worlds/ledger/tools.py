from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def search_vendors(conn: sqlite3.Connection, name: str | None = None) -> dict[str, Any]:
    if name:
        rows = conn.execute(
            "SELECT * FROM vendors WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM vendors ORDER BY name").fetchall()
    return {"vendors": _rows(rows)}


def search_invoices(
    conn: sqlite3.Connection,
    vendor_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if vendor_id:
        clauses.append("vendor_id = ?")
        params.append(vendor_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM invoices {where} ORDER BY invoice_date, id", params).fetchall()
    return {"invoices": _rows(rows)}


def search_payments(
    conn: sqlite3.Connection,
    vendor_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if vendor_id:
        clauses.append("vendor_id = ?")
        params.append(vendor_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM payments {where} ORDER BY payment_date, id", params).fetchall()
    return {"payments": _rows(rows)}


def get_bank_transaction(conn: sqlite3.Connection, transaction_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM bank_transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown bank transaction: {transaction_id}")
    return {"bank_transaction": dict(row)}


def match_payment_to_invoice(conn: sqlite3.Connection, payment_id: str, invoice_id: str) -> dict[str, Any]:
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if payment is None:
        raise ValueError(f"Unknown payment: {payment_id}")
    if invoice is None:
        raise ValueError(f"Unknown invoice: {invoice_id}")
    if payment["vendor_id"] != invoice["vendor_id"]:
        raise ValueError("Payment and invoice vendors do not match")
    if round(float(payment["amount"]), 2) != round(float(invoice["amount"]), 2):
        raise ValueError("Payment and invoice amounts do not match")

    conn.execute(
        "UPDATE payments SET invoice_id = ?, status = 'matched', duplicate_of_payment_id = NULL WHERE id = ?",
        (invoice_id, payment_id),
    )
    conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
    return {"payment_id": payment_id, "invoice_id": invoice_id, "status": "matched"}


def flag_duplicate_payment(
    conn: sqlite3.Connection,
    payment_id: str,
    duplicate_of_payment_id: str,
) -> dict[str, Any]:
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    original = conn.execute("SELECT * FROM payments WHERE id = ?", (duplicate_of_payment_id,)).fetchone()
    if payment is None:
        raise ValueError(f"Unknown payment: {payment_id}")
    if original is None:
        raise ValueError(f"Unknown original payment: {duplicate_of_payment_id}")
    if payment["vendor_id"] != original["vendor_id"]:
        raise ValueError("Duplicate payment must share vendor with original payment")
    if round(float(payment["amount"]), 2) != round(float(original["amount"]), 2):
        raise ValueError("Duplicate payment amount does not match original payment")

    conn.execute(
        """
        UPDATE payments
        SET status = 'duplicate', duplicate_of_payment_id = ?, invoice_id = NULL
        WHERE id = ?
        """,
        (duplicate_of_payment_id, payment_id),
    )
    return {"payment_id": payment_id, "duplicate_of_payment_id": duplicate_of_payment_id, "status": "duplicate"}


def create_journal_entry(
    conn: sqlite3.Connection,
    entry_date: str,
    account: str,
    debit: float,
    credit: float,
    memo: str,
) -> dict[str, Any]:
    cursor = conn.execute(
        """
        INSERT INTO journal_entries (entry_date, account, debit, credit, memo)
        VALUES (?, ?, ?, ?, ?)
        """,
        (entry_date, account, debit, credit, memo),
    )
    return {"journal_entry_id": cursor.lastrowid}


def create_reconciliation_item(
    conn: sqlite3.Connection,
    bank_transaction_id: str,
    description: str,
    amount: float,
    status: str = "open",
) -> dict[str, Any]:
    cursor = conn.execute(
        """
        INSERT INTO reconciliation_items (bank_transaction_id, description, amount, status)
        VALUES (?, ?, ?, ?)
        """,
        (bank_transaction_id, description, amount, status),
    )
    return {"reconciliation_item_id": cursor.lastrowid}


def write_audit_log(
    conn: sqlite3.Connection,
    action: str,
    summary: str,
    task_id: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    cursor = conn.execute(
        """
        INSERT INTO audit_log (task_id, action, record_id, summary, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_id, action, record_id, summary, datetime.now(timezone.utc).isoformat()),
    )
    return {"audit_log_id": cursor.lastrowid}


def mark_close_task_complete(conn: sqlite3.Connection, close_task_id: str) -> dict[str, Any]:
    open_breaks = conn.execute(
        "SELECT COUNT(*) AS count FROM reconciliation_items WHERE status = 'open'"
    ).fetchone()["count"]
    if open_breaks:
        raise ValueError("Cannot complete close task while reconciliation items are open")
    conn.execute(
        "UPDATE close_tasks SET status = 'complete', completed_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), close_task_id),
    )
    return {"close_task_id": close_task_id, "status": "complete"}


TOOLS = {
    "search_vendors": search_vendors,
    "search_invoices": search_invoices,
    "search_payments": search_payments,
    "get_bank_transaction": get_bank_transaction,
    "match_payment_to_invoice": match_payment_to_invoice,
    "flag_duplicate_payment": flag_duplicate_payment,
    "create_journal_entry": create_journal_entry,
    "create_reconciliation_item": create_reconciliation_item,
    "write_audit_log": write_audit_log,
    "mark_close_task_complete": mark_close_task_complete,
}
