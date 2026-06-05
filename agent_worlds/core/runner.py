from __future__ import annotations

import importlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_worlds.agents import model_agent, scripted_agent
from agent_worlds.core.db import connect_world, reset_world
from agent_worlds.core.tasks import get_task, list_tasks
from agent_worlds.core.trajectory import (
    append_jsonl,
    diff_snapshots,
    snapshot_database,
    write_json,
)
from agent_worlds.core.world import get_world_spec
from agent_worlds.curriculum.task_mutator import generate_followups


def default_runs_root() -> Path:
    return Path(os.environ.get("AGENT_WORLDS_RUNS_DIR", Path.cwd() / "runs"))


class ToolRecorder:
    def __init__(self, conn: sqlite3.Connection, registry: dict[str, Callable[..., dict[str, Any]]]) -> None:
        self.conn = conn
        self.registry = registry
        self.calls: list[dict[str, Any]] = []

    def call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        return self._invoke(tool_name, arguments, raise_errors=True)

    def safe_call(self, tool_name: str, **arguments: Any) -> dict[str, Any]:
        return self._invoke(tool_name, arguments, raise_errors=False)

    def _invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raise_errors: bool,
    ) -> dict[str, Any]:
        if tool_name not in self.registry:
            output = {"error": "unknown_tool", "message": f"Unknown tool: {tool_name}"}
            self.calls.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "output": output,
                    "output_summary": output["message"],
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "error",
                }
            )
            if raise_errors:
                raise ValueError(output["message"])
            return output
        started_at = datetime.now(timezone.utc).isoformat()
        status = "ok"
        try:
            output = self.registry[tool_name](self.conn, **arguments)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            status = "error"
            output = {"error": type(exc).__name__, "message": str(exc)}
        finished_at = datetime.now(timezone.utc).isoformat()
        self.calls.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "output": output,
                "output_summary": _summarize_output(output),
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
            }
        )
        if status == "error" and raise_errors:
            raise RuntimeError(output["message"])
        return output


def run_task(
    world_id: str,
    task_id: str,
    agent_id: str = "scripted",
    state_root: Path | None = None,
    runs_root: Path | None = None,
    reset_state: bool = True,
    model: str | None = None,
) -> dict[str, Any]:
    spec = get_world_spec(world_id)
    if reset_state:
        reset_world(spec.id, state_root)
    task = get_task(spec.id, task_id)
    conn = connect_world(spec.id, state_root)
    try:
        tools_module = importlib.import_module(spec.tools_module)
        verifier_module = importlib.import_module(spec.verifier_module)
        recorder = ToolRecorder(conn, tools_module.TOOLS)
        before = snapshot_database(conn)

        agent_metadata: dict[str, Any] = {}
        if agent_id == "scripted":
            scripted_agent.run(spec.id, task, recorder)
        elif agent_id == "model":
            agent_metadata = model_agent.run(spec.id, task, recorder, model=model)
        else:
            raise ValueError("Unknown agent. Expected 'scripted' or 'model'")

        after = snapshot_database(conn)
        state_diff = diff_snapshots(before, after)
        verifier_result = verifier_module.verify(conn, task)
        generated_followups = []
        if not verifier_result["passed"]:
            generated_followups = generate_followups(spec.id, task, verifier_result)

        run_id = _new_run_id(spec.id, task_id)
        run_record = {
            "run_id": run_id,
            "world": spec.id,
            "task_id": task_id,
            "task_prompt": task["prompt"],
            "agent": agent_id,
            "model": agent_metadata.get("model"),
            "agent_final_message": agent_metadata.get("final_message", ""),
            "passed": verifier_result["passed"],
            "reward": verifier_result["reward"],
            "failure_type": verifier_result.get("failure_type"),
            "tool_calls": recorder.calls,
            "state_diff": state_diff,
            "verifier": verifier_result,
            "generated_followups": generated_followups,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _save_run(run_record, runs_root or default_runs_root())
        return run_record
    finally:
        conn.close()


def verify_current_state(
    world_id: str,
    task_id: str,
    state_root: Path | None = None,
) -> dict[str, Any]:
    spec = get_world_spec(world_id)
    task = get_task(spec.id, task_id)
    conn = connect_world(spec.id, state_root)
    try:
        verifier_module = importlib.import_module(spec.verifier_module)
        return verifier_module.verify(conn, task)
    finally:
        conn.close()


def run_curriculum(
    world_id: str,
    agent_id: str = "scripted",
    state_root: Path | None = None,
    runs_root: Path | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    runs = []
    for task in list_tasks(world_id):
        runs.append(
            run_task(
                world_id,
                task["id"],
                agent_id=agent_id,
                state_root=state_root,
                runs_root=runs_root,
                reset_state=True,
                model=model,
            )
        )
    return runs


def _save_run(run_record: dict[str, Any], runs_root: Path) -> None:
    run_id = run_record["run_id"]
    trajectory = {
        "run_id": run_id,
        "world": run_record["world"],
        "task_id": run_record["task_id"],
        "task_prompt": run_record["task_prompt"],
        "agent": run_record["agent"],
        "model": run_record.get("model"),
        "agent_final_message": run_record.get("agent_final_message", ""),
        "tool_calls": run_record["tool_calls"],
        "verifier": run_record["verifier"],
        "state_diff": run_record["state_diff"],
        "generated_followups": run_record["generated_followups"],
    }
    write_json(runs_root / "trajectories" / f"{run_id}.json", trajectory)
    write_json(runs_root / "state_diffs" / f"{run_id}.json", run_record["state_diff"])
    write_json(runs_root / "verifier_results" / f"{run_id}.json", run_record["verifier"])
    append_jsonl(runs_root / "runs.jsonl", run_record)
    for followup in run_record["generated_followups"]:
        item = dict(followup)
        item["parent_run_id"] = run_id
        append_jsonl(runs_root / "generated_tasks.jsonl", item)


def _new_run_id(world_id: str, task_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"run_{world_id}_{task_id}_{stamp}_{suffix}"


def _summarize_output(output: dict[str, Any]) -> str:
    for key, value in output.items():
        if isinstance(value, list):
            return f"{len(value)} {key}"
        if key.endswith("_id"):
            return f"{key}={value}"
    text = json.dumps(output, sort_keys=True)
    return text if len(text) <= 140 else f"{text[:137]}..."
