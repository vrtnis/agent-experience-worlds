from __future__ import annotations

from pathlib import Path

from agent_worlds.core.db import connect_world, reset_world


def test_reset_ledger_seeds_expected_records(tmp_path: Path) -> None:
    db_path = reset_world("ledger", tmp_path)
    assert db_path.exists()
    conn = connect_world("ledger", tmp_path)
    try:
        vendors = conn.execute("SELECT COUNT(*) AS count FROM vendors").fetchone()["count"]
        payments = conn.execute("SELECT COUNT(*) AS count FROM payments").fetchone()["count"]
        assert vendors == 2
        assert payments == 3
    finally:
        conn.close()


def test_reset_contracts_seeds_documents(tmp_path: Path) -> None:
    reset_world("contracts", tmp_path)
    conn = connect_world("contracts", tmp_path)
    try:
        documents = conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]
        assert documents == 2
        body = conn.execute("SELECT body FROM documents WHERE id = 'doc_apex_original'").fetchone()["body"]
        assert "State of Delaware" in body
    finally:
        conn.close()
