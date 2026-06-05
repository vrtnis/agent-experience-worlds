from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_worlds.core.db import describe_world, reset_world
from agent_worlds.core.runner import run_curriculum, run_task, verify_current_state
from agent_worlds.core.tasks import list_tasks
from agent_worlds.core.world import get_world_spec, list_worlds
from agent_worlds.rl.dataset import export_dataset
from agent_worlds.train.prepare_agent import prepare_skyrl_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-exp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    world_parser = subparsers.add_parser("world", help="World maintenance commands")
    world_sub = world_parser.add_subparsers(dest="world_command", required=True)
    world_reset = world_sub.add_parser("reset", help="Reset a world database")
    world_reset.add_argument("world")

    task_parser = subparsers.add_parser("task", help="Task commands")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)
    task_list = task_sub.add_parser("list", help="List world tasks")
    task_list.add_argument("world")

    run_parser = subparsers.add_parser("run", help="Run one task")
    run_parser.add_argument("world")
    run_parser.add_argument("--task", required=True)
    run_parser.add_argument("--agent", default="scripted")
    run_parser.add_argument("--model", help="Model identifier for --agent model")
    run_parser.add_argument("--no-reset", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Verify current world state for a task")
    verify_parser.add_argument("world")
    verify_parser.add_argument("--task", required=True)

    curriculum_parser = subparsers.add_parser("curriculum", help="Curriculum commands")
    curriculum_sub = curriculum_parser.add_subparsers(dest="curriculum_command", required=True)
    curriculum_run = curriculum_sub.add_parser("run", help="Run all seed tasks in a world")
    curriculum_run.add_argument("world")
    curriculum_run.add_argument("--agent", default="scripted")
    curriculum_run.add_argument("--model", help="Model identifier for --agent model")

    rl_parser = subparsers.add_parser("rl", help="RL adapter and dataset commands")
    rl_sub = rl_parser.add_subparsers(dest="rl_command", required=True)
    rl_dataset = rl_sub.add_parser("dataset", help="Export RL-ready task dataset")
    rl_dataset.add_argument("--output-dir", default="data/rl")
    rl_dataset.add_argument("--world", action="append", dest="worlds", help="World to include. Repeat for multiple worlds.")
    rl_dataset.add_argument("--eval-count", type=int, default=1)
    rl_dataset.add_argument("--max-turns", type=int, default=16)
    rl_skyrl_dataset = rl_sub.add_parser("skyrl-dataset", help="Export SkyRL PPO training dataset")
    rl_skyrl_dataset.add_argument("--output-dir", default="data/skyrl")
    rl_skyrl_dataset.add_argument("--world", action="append", dest="worlds", help="World to include. Repeat for multiple worlds.")
    rl_skyrl_dataset.add_argument("--eval-count", type=int, default=1)
    rl_skyrl_dataset.add_argument("--max-turns", type=int, default=16)
    rl_skyrl_dataset.add_argument("--format", choices=("parquet", "jsonl"), default="parquet")

    api_parser = subparsers.add_parser("api", help="API commands")
    api_sub = api_parser.add_subparsers(dest="api_command", required=True)
    api_start = api_sub.add_parser("start", help="Start read-only API")
    api_start.add_argument("--host", default="127.0.0.1")
    api_start.add_argument("--port", type=int, default=8000)

    dashboard_parser = subparsers.add_parser("dashboard", help="Dashboard commands")
    dashboard_sub = dashboard_parser.add_subparsers(dest="dashboard_command", required=True)
    dashboard_start = dashboard_sub.add_parser("start", help="Start dashboard and API")
    dashboard_start.add_argument("--host", default="127.0.0.1")
    dashboard_start.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "world" and args.world_command == "reset":
        path = reset_world(args.world)
        _print_json({"world": get_world_spec(args.world).id, "db_path": str(path), "status": "reset"})
        return 0

    if args.command == "task" and args.task_command == "list":
        _print_json(list_tasks(args.world))
        return 0

    if args.command == "run":
        run = run_task(
            args.world,
            args.task,
            agent_id=args.agent,
            reset_state=not args.no_reset,
            model=args.model,
        )
        _print_json(_compact_run(run))
        return 0

    if args.command == "verify":
        _print_json(verify_current_state(args.world, args.task))
        return 0

    if args.command == "curriculum" and args.curriculum_command == "run":
        runs = run_curriculum(args.world, agent_id=args.agent, model=args.model)
        _print_json(
            {
                "world": get_world_spec(args.world).id,
                "runs": [_compact_run(run) for run in runs],
            }
        )
        return 0

    if args.command == "rl" and args.rl_command == "dataset":
        _print_json(
            export_dataset(
                Path(args.output_dir),
                world_ids=args.worlds,
                eval_count=args.eval_count,
                max_turns=args.max_turns,
            )
        )
        return 0

    if args.command == "rl" and args.rl_command == "skyrl-dataset":
        _print_json(
            prepare_skyrl_dataset(
                Path(args.output_dir),
                world_ids=args.worlds,
                eval_count=args.eval_count,
                max_turns=args.max_turns,
                output_format=args.format,
            )
        )
        return 0

    if args.command == "api" and args.api_command == "start":
        _start_api(args.host, args.port)
        return 0

    if args.command == "dashboard" and args.dashboard_command == "start":
        _start_api(args.host, args.port)
        return 0

    parser.error("Unsupported command")
    return 2


def _start_api(host: str, port: int) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install API dependencies with: python -m pip install -e .[api]") from exc
    from agent_worlds.core.api import create_app

    print(f"Serving Agent Experience Worlds dashboard/API at http://{host}:{port}/", flush=True)
    uvicorn.run(create_app(), host=host, port=port)


def _compact_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "world": run["world"],
        "task_id": run["task_id"],
        "agent": run["agent"],
        "model": run.get("model"),
        "passed": run["passed"],
        "reward": run["reward"],
        "failure_type": run["failure_type"],
        "tool_calls": len(run["tool_calls"]),
        "state_diff_items": len(run["state_diff"]),
        "generated_followups": len(run["generated_followups"]),
    }


def _print_json(item: Any) -> None:
    print(json.dumps(item, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
