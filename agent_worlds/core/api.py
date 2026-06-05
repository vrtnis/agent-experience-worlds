from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from agent_worlds.core.db import describe_world
from agent_worlds.core.runner import default_runs_root
from agent_worlds.core.tasks import all_tasks
from agent_worlds.core.trajectory import read_jsonl
from agent_worlds.core.world import PACKAGE_ROOT, list_worlds


def create_app():
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: python -m pip install -e .[api]") from exc

    app = FastAPI(title="Agent Experience Worlds API")

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        path = PACKAGE_ROOT / "dashboard" / "index.html"
        return path.read_text(encoding="utf-8")

    @app.get("/api/worlds")
    def worlds() -> list[dict[str, Any]]:
        return [describe_world(spec) for spec in list_worlds()]

    @app.get("/api/tasks")
    def tasks() -> list[dict[str, Any]]:
        return all_tasks()

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        return list(reversed([_present_run(run) for run in _runs()]))

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        for run in _runs():
            if run["run_id"] == run_id:
                return _present_run(run)
        return {"error": "run_not_found", "run_id": run_id}

    @app.get("/api/failures")
    def failures() -> dict[str, Any]:
        counts = Counter(run.get("failure_type") for run in _runs() if not run.get("passed"))
        counts.pop(None, None)
        return {"counts": dict(counts)}

    @app.get("/api/curriculum")
    def curriculum() -> list[dict[str, Any]]:
        return read_jsonl(default_runs_root() / "generated_tasks.jsonl")

    @app.get("/api/metrics")
    def metrics() -> dict[str, Any]:
        return _metrics(_runs())

    return app


def _runs() -> list[dict[str, Any]]:
    return read_jsonl(default_runs_root() / "runs.jsonl")


def _present_run(run: dict[str, Any]) -> dict[str, Any]:
    item = dict(run)
    item["agent"] = "scripted" if run.get("agent") == "scripted" else "model"
    item.pop("model", None)
    return item


def _metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {
            "run_count": 0,
            "overall_pass_rate": 0.0,
            "average_reward": 0.0,
            "average_tool_calls": 0.0,
            "pass_rate_by_world": {},
            "failure_type_distribution": {},
            "mutation_count_by_failure_type": {},
        }

    pass_count = sum(1 for run in runs if run.get("passed"))
    rewards = [float(run.get("reward", 0.0)) for run in runs]
    tool_counts = [len(run.get("tool_calls", [])) for run in runs]
    by_world: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_world[run["world"]].append(run)
    pass_rate_by_world = {
        world: round(sum(1 for run in world_runs if run.get("passed")) / len(world_runs), 3)
        for world, world_runs in by_world.items()
    }
    failures = Counter(run.get("failure_type") for run in runs if not run.get("passed"))
    failures.pop(None, None)
    mutations = Counter()
    for item in read_jsonl(default_runs_root() / "generated_tasks.jsonl"):
        mutations[item.get("failure_type", "unknown")] += 1
    return {
        "run_count": len(runs),
        "overall_pass_rate": round(pass_count / len(runs), 3),
        "average_reward": round(sum(rewards) / len(rewards), 3),
        "average_tool_calls": round(sum(tool_counts) / len(tool_counts), 3),
        "pass_rate_by_world": pass_rate_by_world,
        "failure_type_distribution": dict(failures),
        "mutation_count_by_failure_type": dict(mutations),
    }
