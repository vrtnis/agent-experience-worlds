# Agent Experience Worlds

Resettable, verifiable environments where agents learn from tool-use experience.

Agent Experience Worlds provides SQLite-backed task environments with local tools, deterministic verifiers, trajectory logs, failure classification, follow-up task generation, dataset export, and training integration points.

## Worlds

- Ledger reconciliation
- Contract diligence

## Features

- Resettable SQLite worlds
- Tool-based agent actions
- Scripted and model-backed agents
- Deterministic task verifiers
- Failure-driven task generation
- Dataset export for RL workflows
- Training integration adapters
- Local API and dashboard

## Install

```bash
python -m pip install -e ".[api,test]"
```

## Run A Task

```bash
agent-exp world reset ledger
agent-exp run ledger --task duplicate_payment

agent-exp world reset contracts
agent-exp run contracts --task governing_law
```

## Generate Follow-Up Tasks

```bash
agent-exp curriculum run ledger
agent-exp curriculum run contracts
```

## Export Datasets

```bash
agent-exp rl dataset --output-dir data/rl
agent-exp rl skyrl-dataset --output-dir data/skyrl
```

## Start The Dashboard

```bash
agent-exp dashboard start
```

Open:

```text
http://127.0.0.1:8000/
```

## Run Tests

```bash
pytest
```

## Outputs

Generated state and run artifacts are written to:

```text
data/
runs/
```

## How To Cite

```bibtex
@software{agent_experience_worlds,
  title = {Agent Experience Worlds},
  author = {{Agent Experience Worlds contributors}},
  year = {2026},
  url = {https://github.com/vrtnis/agent-experience-worlds}
}
```
