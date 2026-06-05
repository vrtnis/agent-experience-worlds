from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class WorldSpec:
    id: str
    label: str
    db_name: str
    schema_path: Path
    tasks_path: Path
    seed_module: str
    tools_module: str
    verifier_module: str
    summary: str


WORLD_SPECS = {
    "ledger": WorldSpec(
        id="ledger",
        label="Ledger Reconciliation",
        db_name="ledger.sqlite",
        schema_path=PACKAGE_ROOT / "worlds" / "ledger" / "schema.sql",
        tasks_path=PACKAGE_ROOT / "worlds" / "ledger" / "tasks.jsonl",
        seed_module="agent_worlds.worlds.ledger.seed",
        tools_module="agent_worlds.worlds.ledger.tools",
        verifier_module="agent_worlds.worlds.ledger.verifier",
        summary="Synthetic invoice, payment, bank transaction, and close workflow.",
    ),
    "contracts": WorldSpec(
        id="contracts",
        label="Contract Diligence",
        db_name="contracts.sqlite",
        schema_path=PACKAGE_ROOT / "worlds" / "contracts" / "schema.sql",
        tasks_path=PACKAGE_ROOT / "worlds" / "contracts" / "tasks.jsonl",
        seed_module="agent_worlds.worlds.contracts.seed",
        tools_module="agent_worlds.worlds.contracts.tools",
        verifier_module="agent_worlds.worlds.contracts.verifier",
        summary="Synthetic document review, citation, obligation, and matter workflow.",
    ),
}

ALIASES = {
    "contract": "contracts",
    "contracts": "contracts",
    "ledger": "ledger",
}


def normalize_world_id(world_id: str) -> str:
    key = world_id.strip().lower()
    try:
        return ALIASES[key]
    except KeyError as exc:
        valid = ", ".join(sorted(WORLD_SPECS))
        raise ValueError(f"Unknown world '{world_id}'. Expected one of: {valid}") from exc


def get_world_spec(world_id: str) -> WorldSpec:
    return WORLD_SPECS[normalize_world_id(world_id)]


def list_worlds() -> list[WorldSpec]:
    return list(WORLD_SPECS.values())
