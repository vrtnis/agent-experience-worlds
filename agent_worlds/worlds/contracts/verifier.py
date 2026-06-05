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


def _citation_for(conn: sqlite3.Connection, source_table: str, source_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM citations
        WHERE source_table = ? AND source_id = ?
        ORDER BY id
        LIMIT 1
        """,
        (source_table, source_id),
    ).fetchone()


def _verify_governing_law(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    clause = conn.execute(
        """
        SELECT *
        FROM clauses
        WHERE clause_type = 'governing_law' AND document_id = 'doc_apex_original'
        LIMIT 1
        """
    ).fetchone()
    if clause is None or "Delaware" not in clause["text"]:
        return _result(
            False,
            0.0,
            "missing_state_update",
            {
                "expected": "governing law clause extracted from original agreement",
                "observed": dict(clause) if clause else None,
            },
        )
    citation = _citation_for(conn, "clauses", clause["id"])
    if citation is None or "Delaware" not in citation["quote"]:
        return _result(
            False,
            0.5,
            "missing_citation",
            {
                "expected": "citation attached to governing law clause",
                "observed": dict(citation) if citation else "no citation attached",
            },
        )
    if not _audit_contains(conn, task["id"], ["governing", "citation"]):
        return _result(
            False,
            0.75,
            "missing_audit_log",
            {
                "expected": "audit log for governing law citation",
                "observed": "no matching audit_log entry",
            },
        )
    return _result(
        True,
        1.0,
        None,
        {
            "expected": "governing law clause with citation and audit log",
            "observed": "Delaware clause extracted and cited",
        },
    )


def _verify_renewal_deadline(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    obligation = conn.execute(
        "SELECT * FROM obligations WHERE obligation_type = 'renewal_notice' LIMIT 1"
    ).fetchone()
    if obligation is None or "May 1, 2026" not in obligation["description"]:
        return _result(
            False,
            0.0,
            "missing_state_update",
            {
                "expected": "renewal notice obligation referencing May 1, 2026",
                "observed": dict(obligation) if obligation else None,
            },
        )
    deadline = conn.execute(
        "SELECT * FROM deadlines WHERE obligation_id = ?",
        (obligation["id"],),
    ).fetchone()
    if deadline is None or deadline["due_date"] != "2026-05-01":
        return _result(
            False,
            0.5,
            "bad_calculation",
            {
                "expected": "deadline due_date 2026-05-01",
                "observed": dict(deadline) if deadline else None,
            },
        )
    citation = _citation_for(conn, "obligations", obligation["id"])
    if citation is None or "May 1, 2026" not in citation["quote"]:
        return _result(
            False,
            0.75,
            "missing_citation",
            {
                "expected": "citation attached to renewal notice obligation",
                "observed": dict(citation) if citation else "no citation attached",
            },
        )
    if not _audit_contains(conn, task["id"], ["renewal", "deadline"]):
        return _result(
            False,
            0.75,
            "missing_audit_log",
            {
                "expected": "audit log for renewal deadline",
                "observed": "no matching audit_log entry",
            },
        )
    return _result(
        True,
        1.0,
        None,
        {
            "expected": "renewal obligation, deadline, citation, and audit log",
            "observed": "renewal deadline recorded for 2026-05-01",
        },
    )


def _verify_termination_amendment(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    clause = conn.execute(
        """
        SELECT *
        FROM clauses
        WHERE clause_type = 'termination'
          AND document_id = 'doc_apex_amendment_1'
        LIMIT 1
        """
    ).fetchone()
    if clause is None or "30 days written notice" not in clause["text"]:
        return _result(
            False,
            0.0,
            "missing_state_update",
            {
                "expected": "amended termination language extracted from amendment",
                "observed": dict(clause) if clause else None,
            },
        )
    citation = _citation_for(conn, "clauses", clause["id"])
    if citation is None or "30 days written notice" not in citation["quote"]:
        return _result(
            False,
            0.5,
            "missing_citation",
            {
                "expected": "citation attached to amended termination clause",
                "observed": dict(citation) if citation else "no citation attached",
            },
        )
    if not _audit_contains(conn, task["id"], ["termination", "amendment"]):
        return _result(
            False,
            0.75,
            "missing_audit_log",
            {
                "expected": "audit log for amended termination review",
                "observed": "no matching audit_log entry",
            },
        )
    return _result(
        True,
        1.0,
        None,
        {
            "expected": "amended termination clause with citation and audit log",
            "observed": "30-day termination language extracted and cited",
        },
    )


def verify(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    verifier_id = task.get("verifier", task["id"])
    if verifier_id == "governing_law":
        return _verify_governing_law(conn, task)
    if verifier_id == "renewal_deadline":
        return _verify_renewal_deadline(conn, task)
    if verifier_id == "termination_amendment":
        return _verify_termination_amendment(conn, task)
    return _result(
        False,
        0.0,
        "wrong_tool",
        {
            "expected": "known contract verifier",
            "observed": verifier_id,
        },
    )
