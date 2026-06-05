from __future__ import annotations

import sqlite3
from typing import Any


def _result(
    passed: bool,
    reward: float,
    failure_type: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "passed": passed,
        "reward": reward,
        "failure_type": failure_type,
        "details": details or {},
    }


def _audit_contains(conn: sqlite3.Connection, task_id: str, terms: list[str]) -> bool:
    rows = conn.execute(
        "SELECT action, summary FROM audit_log WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    haystack = "\n".join(f"{row['action']} {row['summary']}" for row in rows).lower()
    return bool(haystack) and all(term.lower() in haystack for term in terms)


def _verify_duplicate_payment(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    duplicate = conn.execute("SELECT * FROM payments WHERE id = 'pay_orion_002'").fetchone()
    vega = conn.execute("SELECT * FROM payments WHERE id = 'pay_vega_001'").fetchone()
    if duplicate["status"] != "duplicate" or duplicate["duplicate_of_payment_id"] != "pay_orion_001":
        return _result(
            False,
            0.0,
            "missing_state_update",
            {
                "expected": "pay_orion_002 flagged as duplicate of pay_orion_001",
                "observed": dict(duplicate),
            },
        )
    if vega["status"] != "unmatched" or vega["invoice_id"] is not None:
        return _result(
            False,
            0.0,
            "wrong_record_updated",
            {
                "expected": "Vega payment remains untouched",
                "observed": dict(vega),
            },
        )
    if not _audit_contains(conn, task["id"], ["duplicate", "orion"]):
        return _result(
            False,
            0.5,
            "missing_audit_log",
            {
                "expected": "audit log for Orion duplicate payment",
                "observed": "no matching audit_log entry",
            },
        )
    return _result(
        True,
        1.0,
        None,
        {
            "expected": "duplicate payment flagged and audit log written",
            "observed": "pay_orion_002 marked duplicate with audit evidence",
        },
    )


def _verify_match_vega_payment(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    payment = conn.execute("SELECT * FROM payments WHERE id = 'pay_vega_001'").fetchone()
    invoice = conn.execute("SELECT * FROM invoices WHERE id = 'inv_vega_2001'").fetchone()
    orion_duplicate = conn.execute("SELECT * FROM payments WHERE id = 'pay_orion_002'").fetchone()
    if payment["status"] != "matched" or payment["invoice_id"] != "inv_vega_2001":
        return _result(
            False,
            0.0,
            "missing_state_update",
            {
                "expected": "pay_vega_001 matched to inv_vega_2001",
                "observed": dict(payment),
            },
        )
    if invoice["status"] != "paid":
        return _result(
            False,
            0.5,
            "incomplete_workflow",
            {
                "expected": "inv_vega_2001 status paid",
                "observed": dict(invoice),
            },
        )
    if orion_duplicate["status"] != "unmatched":
        return _result(
            False,
            0.0,
            "wrong_record_updated",
            {
                "expected": "Orion duplicate candidate remains untouched",
                "observed": dict(orion_duplicate),
            },
        )
    if not _audit_contains(conn, task["id"], ["matched", "vega"]):
        return _result(
            False,
            0.5,
            "missing_audit_log",
            {
                "expected": "audit log for Vega payment match",
                "observed": "no matching audit_log entry",
            },
        )
    return _result(
        True,
        1.0,
        None,
        {
            "expected": "Vega payment matched with audit evidence",
            "observed": "pay_vega_001 matched to inv_vega_2001",
        },
    )


def verify(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    verifier_id = task.get("verifier", task["id"])
    if verifier_id == "duplicate_payment":
        return _verify_duplicate_payment(conn, task)
    if verifier_id == "match_vega_payment":
        return _verify_match_vega_payment(conn, task)
    return _result(
        False,
        0.0,
        "wrong_tool",
        {
            "expected": "known ledger verifier",
            "observed": verifier_id,
        },
    )
