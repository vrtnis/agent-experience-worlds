from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

from agent_worlds.core.world import WorldSpec, get_world_spec


def default_state_root() -> Path:
    return Path(os.environ.get("AGENT_WORLDS_STATE_DIR", Path.cwd() / "data"))


def world_db_path(world_id: str, state_root: Path | None = None) -> Path:
    spec = get_world_spec(world_id)
    root = state_root or default_state_root()
    return root / spec.db_name


def connect_world(world_id: str, state_root: Path | None = None, create_if_missing: bool = True) -> sqlite3.Connection:
    path = world_db_path(world_id, state_root)
    if not path.exists():
        if not create_if_missing:
            raise FileNotFoundError(f"World database does not exist: {path}")
        reset_world(world_id, state_root)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def reset_world(world_id: str, state_root: Path | None = None) -> Path:
    spec = get_world_spec(world_id)
    root = state_root or default_state_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / spec.db_name
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    schema = spec.schema_path.read_text(encoding="utf-8")
    conn.executescript(schema)
    seed_module = importlib.import_module(spec.seed_module)
    seed_module.seed(conn)
    conn.commit()
    conn.close()
    return path


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row["name"] for row in rows]


def describe_world(spec: WorldSpec, state_root: Path | None = None) -> dict:
    path = world_db_path(spec.id, state_root)
    return {
        "id": spec.id,
        "label": spec.label,
        "summary": spec.summary,
        "db_path": str(path),
        "exists": path.exists(),
    }
