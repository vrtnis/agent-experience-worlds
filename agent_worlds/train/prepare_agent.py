from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from agent_worlds.rl.dataset import build_rows


def prepare_skyrl_dataset(
    output_dir: Path,
    world_ids: Sequence[str] | None = None,
    eval_count: int = 1,
    max_turns: int = 16,
    output_format: str = "parquet",
) -> dict[str, Any]:
    rows = build_skyrl_rows(world_ids=world_ids, max_turns=max_turns)
    validation_count = min(max(eval_count, 0), len(rows))
    train_rows = rows[: len(rows) - validation_count]
    validation_rows = rows[len(rows) - validation_count :]

    output_dir.mkdir(parents=True, exist_ok=True)
    if output_format == "jsonl":
        train_path = output_dir / "train.jsonl"
        validation_path = output_dir / "validation.jsonl"
        _write_jsonl(train_path, train_rows)
        _write_jsonl(validation_path, validation_rows)
    elif output_format == "parquet":
        train_path = output_dir / "train.parquet"
        validation_path = output_dir / "validation.parquet"
        _write_parquet(train_path, train_rows)
        _write_parquet(validation_path, validation_rows)
    else:
        raise ValueError("output_format must be 'parquet' or 'jsonl'")

    manifest = {
        "format": f"agent_worlds_skyrl_{output_format}_v1",
        "env_id": "agent_worlds",
        "env_class": "agent_worlds.train.skyrl_env:SkyRLAgentEnv",
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "max_turns": max_turns,
        "train_path": str(train_path),
        "validation_path": str(validation_path),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {"output_dir": str(output_dir), "manifest_path": str(manifest_path), **manifest}


def build_skyrl_rows(world_ids: Sequence[str] | None = None, max_turns: int = 16) -> list[dict[str, Any]]:
    rows = []
    for row in build_rows(world_ids=world_ids, max_turns=max_turns):
        rows.append(
            {
                "data_source": "agent_worlds",
                "prompt": row["prompt"],
                "env_class": "agent_worlds",
                "reward_spec": {
                    "method": "deterministic_verifier",
                    "ground_truth": {
                        "world": row["world"],
                        "task_id": row["task_id"],
                    },
                },
                "extra_info": {
                    "world": row["world"],
                    "task_id": row["task_id"],
                    "max_turns": max_turns,
                    "family": row.get("family"),
                    "difficulty": row.get("difficulty"),
                },
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare agent-world task rows for SkyRL PPO training.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/skyrl"))
    parser.add_argument("--world", action="append", dest="worlds", help="World to include. Repeat for multiple worlds.")
    parser.add_argument("--eval-count", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--format", choices=("parquet", "jsonl"), default="parquet")
    args = parser.parse_args(argv)

    summary = prepare_skyrl_dataset(
        output_dir=args.output_dir,
        world_ids=args.worlds,
        eval_count=args.eval_count,
        max_turns=args.max_turns,
        output_format=args.format,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import datasets
    except ImportError as exc:
        raise RuntimeError('Install training dependencies with: python -m pip install -e ".[train]"') from exc
    datasets.Dataset.from_list(rows).to_parquet(str(path))


if __name__ == "__main__":
    raise SystemExit(main())
