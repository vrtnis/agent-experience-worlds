from __future__ import annotations

from pathlib import Path

from agent_worlds.core.runner import run_task


def test_ledger_duplicate_payment_passes(tmp_path: Path) -> None:
    run = run_task(
        "ledger",
        "duplicate_payment",
        state_root=tmp_path / "data",
        runs_root=tmp_path / "runs",
    )
    assert run["passed"] is True
    assert run["reward"] == 1.0
    assert run["failure_type"] is None
    assert any(diff["table"] == "payments" and diff["record_id"] == "pay_orion_002" for diff in run["state_diff"])


def test_ledger_missing_audit_fails_and_generates_followups(tmp_path: Path) -> None:
    run = run_task(
        "ledger",
        "duplicate_payment_missing_audit",
        state_root=tmp_path / "data",
        runs_root=tmp_path / "runs",
    )
    assert run["passed"] is False
    assert run["failure_type"] == "missing_audit_log"
    assert run["reward"] == 0.5
    assert len(run["generated_followups"]) == 5


def test_contract_governing_law_passes(tmp_path: Path) -> None:
    run = run_task(
        "contracts",
        "governing_law",
        state_root=tmp_path / "data",
        runs_root=tmp_path / "runs",
    )
    assert run["passed"] is True
    assert run["reward"] == 1.0
    assert any(diff["table"] == "citations" for diff in run["state_diff"])


def test_contract_missing_citation_fails_and_generates_followups(tmp_path: Path) -> None:
    run = run_task(
        "contracts",
        "termination_missing_citation",
        state_root=tmp_path / "data",
        runs_root=tmp_path / "runs",
    )
    assert run["passed"] is False
    assert run["failure_type"] == "missing_citation"
    assert len(run["generated_followups"]) == 5
