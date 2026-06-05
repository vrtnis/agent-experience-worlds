from __future__ import annotations

import json
from pathlib import Path

from agent_worlds.rl import AgentTextEnv, export_dataset


def test_rl_env_scores_successful_tool_episode(tmp_path: Path) -> None:
    env = AgentTextEnv(state_root=tmp_path / "data", max_turns=8)
    observation = env.reset("ledger", "duplicate_payment")
    assert "duplicate_payment" in observation

    env.step({"tool": "search_vendors", "arguments": {"name": "Orion"}})
    env.step({"tool": "search_payments", "arguments": {"vendor_id": "ven_orion"}})
    env.step(
        {
            "tool": "flag_duplicate_payment",
            "arguments": {
                "payment_id": "pay_orion_002",
                "duplicate_of_payment_id": "pay_orion_001",
            },
        }
    )
    env.step(
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
    result = env.step({"action": "done"})

    assert result.done is True
    assert result.reward == 1.0
    assert result.metadata["passed"] is True
    assert result.metadata["failure_type"] is None
    assert any(call["tool"] == "flag_duplicate_payment" for call in result.metadata["tool_calls"])


def test_rl_env_returns_partial_reward_and_followups(tmp_path: Path) -> None:
    env = AgentTextEnv(state_root=tmp_path / "data", max_turns=8)
    env.reset("ledger", "duplicate_payment_missing_audit")
    env.step({"tool": "search_vendors", "arguments": {"name": "Orion"}})
    env.step({"tool": "search_payments", "arguments": {"vendor_id": "ven_orion"}})
    env.step(
        {
            "tool": "flag_duplicate_payment",
            "arguments": {
                "payment_id": "pay_orion_002",
                "duplicate_of_payment_id": "pay_orion_001",
            },
        }
    )
    result = env.step("DONE")

    assert result.done is True
    assert result.reward == 0.5
    assert result.metadata["passed"] is False
    assert result.metadata["failure_type"] == "missing_audit_log"
    assert len(result.metadata["generated_followups"]) == 5


def test_export_rl_dataset_writes_train_validation_and_manifest(tmp_path: Path) -> None:
    summary = export_dataset(tmp_path / "rl", eval_count=2, max_turns=12)

    train_rows = _read_jsonl(Path(summary["train_path"]))
    validation_rows = _read_jsonl(Path(summary["validation_path"]))
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))

    assert summary["train_rows"] == 4
    assert summary["validation_rows"] == 2
    assert len(train_rows) == 4
    assert len(validation_rows) == 2
    assert manifest["env_class"] == "agent_worlds.rl.env:AgentTextEnv"
    assert train_rows[0]["reward_spec"]["method"] == "deterministic_verifier"
    assert train_rows[0]["extra_info"]["max_turns"] == 12


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
