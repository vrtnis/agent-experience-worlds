from __future__ import annotations

from pathlib import Path

import pytest

from agent_worlds.core import api
from agent_worlds.core.runner import run_task


def test_api_metrics_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AGENT_WORLDS_RUNS_DIR", str(tmp_path / "runs"))
    run_task(
        "ledger",
        "duplicate_payment",
        state_root=tmp_path / "data",
        runs_root=tmp_path / "runs",
    )
    client = TestClient(api.create_app())
    response = client.get("/api/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_count"] == 1
    assert payload["overall_pass_rate"] == 1.0
