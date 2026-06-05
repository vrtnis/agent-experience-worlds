from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agent_worlds.core.db import table_names


def snapshot_database(conn: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
    snapshot: dict[str, dict[str, dict[str, Any]]] = {}
    for table in table_names(conn):
        rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
        table_snapshot: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            record = dict(row)
            record_id = str(record.get("id", index))
            table_snapshot[record_id] = record
        snapshot[table] = table_snapshot
    return snapshot


def diff_snapshots(
    before: dict[str, dict[str, dict[str, Any]]],
    after: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for table in sorted(set(before) | set(after)):
        before_rows = before.get(table, {})
        after_rows = after.get(table, {})
        for record_id in sorted(set(before_rows) | set(after_rows)):
            previous = before_rows.get(record_id)
            current = after_rows.get(record_id)
            if previous is None:
                diffs.append(
                    {
                        "table": table,
                        "record_id": record_id,
                        "field": "*",
                        "before": None,
                        "after": current,
                        "change": "insert",
                    }
                )
                continue
            if current is None:
                diffs.append(
                    {
                        "table": table,
                        "record_id": record_id,
                        "field": "*",
                        "before": previous,
                        "after": None,
                        "change": "delete",
                    }
                )
                continue
            for field in sorted(set(previous) | set(current)):
                old_value = previous.get(field)
                new_value = current.get(field)
                if old_value != new_value:
                    diffs.append(
                        {
                            "table": table,
                            "record_id": record_id,
                            "field": field,
                            "before": old_value,
                            "after": new_value,
                            "change": "update",
                        }
                    )
    return diffs


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, sort_keys=True) + "\n")


def write_json(path: Path, item: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
