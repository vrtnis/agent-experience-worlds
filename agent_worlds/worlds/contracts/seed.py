from __future__ import annotations

import sqlite3
from pathlib import Path


DOC_ROOT = Path(__file__).resolve().parent / "documents"


def _read_doc(name: str) -> str:
    return (DOC_ROOT / name).read_text(encoding="utf-8")


def seed(conn: sqlite3.Connection) -> None:
    original = _read_doc("original_agreement.txt")
    amendment = _read_doc("amendment_1.txt")
    conn.executemany(
        "INSERT INTO documents (id, title, version, path, body) VALUES (?, ?, ?, ?, ?)",
        [
            ("doc_apex_original", "Master Services Agreement", "original", "documents/original_agreement.txt", original),
            ("doc_apex_amendment_1", "Amendment No. 1", "amendment_1", "documents/amendment_1.txt", amendment),
        ],
    )
    conn.execute(
        """
        INSERT INTO contracts (id, name, document_id, effective_date)
        VALUES (?, ?, ?, ?)
        """,
        ("ctr_apex", "Apex Robotics / Northstar MSA", "doc_apex_original", "2026-01-15"),
    )
    conn.executemany(
        "INSERT INTO parties (id, contract_id, name, role) VALUES (?, ?, ?, ?)",
        [
            ("party_apex", "ctr_apex", "Apex Robotics Inc.", "customer"),
            ("party_northstar", "ctr_apex", "Northstar Legal Ops LLC", "vendor"),
        ],
    )
    conn.execute(
        "INSERT INTO matter_status (id, contract_id, status, updated_at) VALUES (?, ?, ?, ?)",
        ("matter_apex", "ctr_apex", "in_review", None),
    )
