from __future__ import annotations

import json
from pathlib import Path

from agent_worlds.train.prepare_agent import build_skyrl_rows, prepare_skyrl_dataset
from agent_worlds.train.skyrl_env import SkyRLAgentEnv


def test_skyrl_rows_use_agent_world_env_contract() -> None:
    rows = build_skyrl_rows(world_ids=["ledger"], max_turns=9)

    assert len(rows) == 3
    assert rows[0]["data_source"] == "agent_worlds"
    assert rows[0]["env_class"] == "agent_worlds"
    assert rows[0]["reward_spec"]["method"] == "deterministic_verifier"
    assert rows[0]["extra_info"]["max_turns"] == 9


def test_prepare_skyrl_dataset_jsonl(tmp_path: Path) -> None:
    summary = prepare_skyrl_dataset(
        tmp_path / "skyrl",
        world_ids=["ledger"],
        eval_count=1,
        max_turns=10,
        output_format="jsonl",
    )

    train_rows = _read_jsonl(Path(summary["train_path"]))
    validation_rows = _read_jsonl(Path(summary["validation_path"]))

    assert summary["env_id"] == "agent_worlds"
    assert summary["train_rows"] == 2
    assert summary["validation_rows"] == 1
    assert len(train_rows) == 2
    assert len(validation_rows) == 1


def test_skyrl_env_wrapper_scores_episode(tmp_path: Path) -> None:
    env = SkyRLAgentEnv(
        extras={
            "extra_info": {
                "world": "ledger",
                "task_id": "duplicate_payment",
                "state_root": str(tmp_path / "data"),
                "max_turns": 8,
            }
        }
    )

    env.step(json.dumps({"tool": "search_vendors", "arguments": {"name": "Orion"}}))
    env.step(json.dumps({"tool": "search_payments", "arguments": {"vendor_id": "ven_orion"}}))
    env.step(
        json.dumps(
            {
                "tool": "flag_duplicate_payment",
                "arguments": {
                    "payment_id": "pay_orion_002",
                    "duplicate_of_payment_id": "pay_orion_001",
                },
            }
        )
    )
    env.step(
        json.dumps(
            {
                "tool": "write_audit_log",
                "arguments": {
                    "task_id": "duplicate_payment",
                    "action": "flag_duplicate_payment",
                    "record_id": "pay_orion_002",
                    "summary": "Flagged duplicate payment for Orion Office Supply.",
                },
            }
        )
    )
    result = env.step(json.dumps({"action": "done"}))

    assert result.done is True
    assert result.reward == 1.0
    assert result.metadata["goal_reached"] is True
    assert result.metadata["env_cleaned_up"] is True


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
