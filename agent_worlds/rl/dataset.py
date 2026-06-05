from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Sequence

from agent_worlds.core.tasks import list_tasks
from agent_worlds.core.world import get_world_spec, list_worlds
from agent_worlds.rl.env import action_contract, tool_contract


SYSTEM_PROMPT = """You are a tool-use agent in a resettable agent world.
Use JSON actions only. Call one tool at a time, inspect tool outputs, and finish with {"action":"done"}.
The final reward is assigned by a deterministic verifier over the resulting world state."""


def export_dataset(
    output_dir: Path,
    world_ids: Sequence[str] | None = None,
    eval_count: int = 1,
    max_turns: int = 16,
) -> dict[str, Any]:
    rows = build_rows(world_ids=world_ids, max_turns=max_turns)
    validation_count = min(max(eval_count, 0), len(rows))
    train_rows = rows[: len(rows) - validation_count]
    validation_rows = rows[len(rows) - validation_count :]

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "train.jsonl", train_rows)
    _write_jsonl(output_dir / "validation.jsonl", validation_rows)
    manifest = {
        "format": "agent_worlds_rl_jsonl_v1",
        "env_class": "agent_worlds.rl.env:AgentTextEnv",
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "max_turns": max_turns,
        "reward": "deterministic verifier reward in [0.0, 1.0]",
        "action_contract": action_contract(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "output_dir": str(output_dir),
        "train_path": str(output_dir / "train.jsonl"),
        "validation_path": str(output_dir / "validation.jsonl"),
        "manifest_path": str(output_dir / "manifest.json"),
        **manifest,
    }


def build_rows(world_ids: Sequence[str] | None = None, max_turns: int = 16) -> list[dict[str, Any]]:
    specs = [get_world_spec(world_id) for world_id in world_ids] if world_ids else list_worlds()
    rows = []
    for spec in specs:
        tools_module = importlib.import_module(spec.tools_module)
        tools = tool_contract(tools_module.TOOLS)
        for task in list_tasks(spec.id):
            rows.append(
                {
                    "id": f"{spec.id}:{task['id']}",
                    "world": spec.id,
                    "task_id": task["id"],
                    "family": task.get("family"),
                    "difficulty": task.get("difficulty"),
                    "prompt": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": _user_prompt(spec.id, task, tools)},
                    ],
                    "env_class": "agent_worlds.rl.env:AgentTextEnv",
                    "reward_spec": {
                        "method": "deterministic_verifier",
                        "world": spec.id,
                        "task_id": task["id"],
                        "range": [0.0, 1.0],
                    },
                    "extra_info": {
                        "world": spec.id,
                        "task_id": task["id"],
                        "max_turns": max_turns,
                    },
                }
            )
    return rows


def _user_prompt(world_id: str, task: dict[str, Any], tools: dict[str, Any]) -> str:
    payload = {
        "world": world_id,
        "task_id": task["id"],
        "task_prompt": task["prompt"],
        "available_tools": tools,
        "action_contract": action_contract(),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
