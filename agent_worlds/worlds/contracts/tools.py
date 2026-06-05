from __future__ import annotations

import sqlite3
import re
from datetime import datetime, timezone
from typing import Any


CLAUSE_PATTERNS = {
    "governing_law": "This agreement is governed by the laws of the State of Delaware.",
    "renewal_notice": "A renewal notice must be delivered no later than May 1, 2026.",
    "termination": "Either party may terminate for convenience with 30 days written notice after the initial term.",
}


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _contract_id_for_document(conn: sqlite3.Connection, document_id: str) -> str:
    row = conn.execute("SELECT id FROM contracts WHERE document_id = ?", (document_id,)).fetchone()
    if row:
        return row["id"]
    fallback = conn.execute("SELECT id FROM contracts ORDER BY id LIMIT 1").fetchone()
    if fallback is None:
        raise ValueError("No contract is available for document")
    return fallback["id"]


def search_documents(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    terms = [term for term in re.split(r"[^A-Za-z0-9]+", query) if len(term) >= 3]
    if not terms:
        terms = [query]
    clauses = " OR ".join(["title LIKE ? OR body LIKE ?" for _ in terms])
    params: list[str] = []
    for term in terms:
        pattern = f"%{term}%"
        params.extend([pattern, pattern])
    rows = conn.execute(
        f"""
        SELECT id, title, version, path, body
        FROM documents
        WHERE {clauses}
        ORDER BY id
        """,
        params,
    ).fetchall()
    documents = []
    for row in rows:
        body = row["body"]
        match_index = body.lower().find(query.lower())
        start = max(match_index - 40, 0) if match_index >= 0 else 0
        snippet = body[start : start + 160].replace("\n", " ")
        item = dict(row)
        item.pop("body")
        item["snippet"] = snippet
        documents.append(item)
    return {"documents": documents}


def get_document(conn: sqlite3.Connection, document_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown document: {document_id}")
    return {"document": dict(row)}


def extract_clause(conn: sqlite3.Connection, document_id: str, clause_type: str) -> dict[str, Any]:
    document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if document is None:
        raise ValueError(f"Unknown document: {document_id}")
    try:
        clause_text = CLAUSE_PATTERNS[clause_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported clause type: {clause_type}") from exc
    start = document["body"].find(clause_text)
    if start < 0:
        raise ValueError(f"Clause type '{clause_type}' not found in {document_id}")
    end = start + len(clause_text)
    contract_id = _contract_id_for_document(conn, document_id)
    clause_id = f"clause_{document_id}_{clause_type}"
    conn.execute(
        """
        INSERT OR REPLACE INTO clauses
          (id, contract_id, document_id, clause_type, text, start_char, end_char)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (clause_id, contract_id, document_id, clause_type, clause_text, start, end),
    )
    return {
        "clause_id": clause_id,
        "contract_id": contract_id,
        "document_id": document_id,
        "clause_type": clause_type,
        "text": clause_text,
        "start_char": start,
        "end_char": end,
    }


def compare_versions(
    conn: sqlite3.Connection,
    original_document_id: str,
    amended_document_id: str,
    topic: str,
) -> dict[str, Any]:
    original = get_document(conn, original_document_id)["document"]
    amended = get_document(conn, amended_document_id)["document"]
    return {
        "topic": topic,
        "original_document_id": original_document_id,
        "amended_document_id": amended_document_id,
        "summary": f"Compared {topic} language between {original['title']} and {amended['title']}.",
    }


def create_obligation(
    conn: sqlite3.Connection,
    contract_id: str,
    obligation_type: str,
    description: str,
    source_clause_id: str | None = None,
) -> dict[str, Any]:
    obligation_id = f"obl_{contract_id}_{obligation_type}"
    conn.execute(
        """
        INSERT OR REPLACE INTO obligations
          (id, contract_id, obligation_type, description, source_clause_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (obligation_id, contract_id, obligation_type, description, source_clause_id),
    )
    return {"obligation_id": obligation_id}


def create_deadline(
    conn: sqlite3.Connection,
    obligation_id: str,
    due_date: str,
    description: str,
) -> dict[str, Any]:
    deadline_id = f"deadline_{obligation_id}"
    conn.execute(
        """
        INSERT OR REPLACE INTO deadlines (id, obligation_id, due_date, description)
        VALUES (?, ?, ?, ?)
        """,
        (deadline_id, obligation_id, due_date, description),
    )
    return {"deadline_id": deadline_id}


def add_risk(
    conn: sqlite3.Connection,
    contract_id: str,
    risk_type: str,
    severity: str,
    summary: str,
) -> dict[str, Any]:
    risk_id = f"risk_{contract_id}_{risk_type}"
    conn.execute(
        """
        INSERT OR REPLACE INTO risks (id, contract_id, risk_type, severity, summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (risk_id, contract_id, risk_type, severity, summary),
    )
    return {"risk_id": risk_id}


def attach_citation(
    conn: sqlite3.Connection,
    source_table: str,
    source_id: str,
    document_id: str,
    start_char: int,
    end_char: int,
    quote: str,
) -> dict[str, Any]:
    document = conn.execute("SELECT body FROM documents WHERE id = ?", (document_id,)).fetchone()
    if document is None:
        raise ValueError(f"Unknown document: {document_id}")
    observed_quote = document["body"][start_char:end_char]
    if observed_quote != quote:
        raise ValueError("Citation span does not match quote")
    cursor = conn.execute(
        """
        INSERT INTO citations
          (source_table, source_id, document_id, start_char, end_char, quote)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_table, source_id, document_id, start_char, end_char, quote),
    )
    return {"citation_id": cursor.lastrowid}


def update_matter_status(conn: sqlite3.Connection, matter_status_id: str, status: str) -> dict[str, Any]:
    conn.execute(
        "UPDATE matter_status SET status = ?, updated_at = ? WHERE id = ?",
        (status, datetime.now(timezone.utc).isoformat(), matter_status_id),
    )
    return {"matter_status_id": matter_status_id, "status": status}


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


TOOLS = {
    "search_documents": search_documents,
    "get_document": get_document,
    "extract_clause": extract_clause,
    "compare_versions": compare_versions,
    "create_obligation": create_obligation,
    "create_deadline": create_deadline,
    "add_risk": add_risk,
    "attach_citation": attach_citation,
    "update_matter_status": update_matter_status,
    "write_audit_log": write_audit_log,
}
