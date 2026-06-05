from __future__ import annotations

import sqlite3


def seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO vendors (id, name, category) VALUES (?, ?, ?)",
        [
            ("ven_orion", "Orion Office Supply", "office_supplies"),
            ("ven_vega", "Vega Analytics", "software"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO invoices
          (id, vendor_id, invoice_number, amount, invoice_date, due_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("inv_orion_1001", "ven_orion", "O-1001", 1200.00, "2026-03-01", "2026-03-31", "paid"),
            ("inv_vega_2001", "ven_vega", "V-2001", 850.00, "2026-03-05", "2026-04-04", "open"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO payments
          (id, vendor_id, invoice_id, amount, payment_date, status, duplicate_of_payment_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("pay_orion_001", "ven_orion", "inv_orion_1001", 1200.00, "2026-03-12", "matched", None),
            ("pay_orion_002", "ven_orion", None, 1200.00, "2026-03-13", "unmatched", None),
            ("pay_vega_001", "ven_vega", None, 850.00, "2026-03-18", "unmatched", None),
        ],
    )
    conn.executemany(
        """
        INSERT INTO bank_transactions
          (id, payment_id, transaction_date, description, amount, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("txn_orion_001", "pay_orion_001", "2026-03-12", "ACH Orion Office Supply O-1001", -1200.00, "cleared"),
            ("txn_orion_002", "pay_orion_002", "2026-03-13", "ACH Orion Office Supply duplicate O-1001", -1200.00, "cleared"),
            ("txn_vega_001", "pay_vega_001", "2026-03-18", "ACH Vega Analytics V-2001", -850.00, "cleared"),
        ],
    )
    conn.execute(
        "INSERT INTO close_tasks (id, title, status, completed_at) VALUES (?, ?, ?, ?)",
        ("march_cash_close", "Complete March cash reconciliation", "open", None),
    )
