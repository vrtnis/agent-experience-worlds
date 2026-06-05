from __future__ import annotations

import json
from pathlib import Path

from agent_worlds.core.world import get_world_spec


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def list_tasks(world_id: str) -> list[dict]:
    spec = get_world_spec(world_id)
    return _load_jsonl(spec.tasks_path)


def get_task(world_id: str, task_id: str) -> dict:
    for task in list_tasks(world_id):
        if task["id"] == task_id:
            return task
    raise ValueError(f"Unknown task '{task_id}' for world '{world_id}'")


def all_tasks() -> list[dict]:
    tasks = []
    for world_id in ("ledger", "contracts"):
        for task in list_tasks(world_id):
            item = dict(task)
            item["world"] = world_id
            tasks.append(item)
    return tasks
