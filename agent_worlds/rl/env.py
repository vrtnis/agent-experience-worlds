from __future__ import annotations

import importlib
import inspect
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent_worlds.core.db import connect_world, reset_world
from agent_worlds.core.runner import ToolRecorder
from agent_worlds.core.tasks import get_task
from agent_worlds.core.trajectory import diff_snapshots, snapshot_database
from agent_worlds.core.world import WorldSpec, get_world_spec
from agent_worlds.curriculum.task_mutator import generate_followups


@dataclass(frozen=True)
class StepResult:
    observation: str
    reward: float
    done: bool
    metadata: dict[str, Any]


class AgentTextEnv:
    """Text-action RL adapter over a resettable agent world.

    Actions are JSON objects:

    - {"tool": "tool_name", "arguments": {...}}
    - {"action": "done"}

    The environment returns zero intermediate reward. On "done" or max turns,
    it runs the world verifier and returns that verifier reward.
    """

    def __init__(
        self,
        world_id: str | None = None,
        task_id: str | None = None,
        state_root: Path | None = None,
        max_turns: int = 16,
        reset_state: bool = True,
    ) -> None:
        self.default_world_id = world_id
        self.default_task_id = task_id
        self.state_root = state_root
        self.max_turns = max_turns
        self.reset_state = reset_state

        self.spec: WorldSpec | None = None
        self.task: dict[str, Any] | None = None
        self.conn: sqlite3.Connection | None = None
        self.recorder: ToolRecorder | None = None
        self.verifier_module: Any = None
        self.before_snapshot: dict[str, dict[str, dict[str, Any]]] | None = None
        self.turns = 0
        self.done = False
        self.last_result: StepResult | None = None

    def reset(self, world_id: str | None = None, task_id: str | None = None) -> str:
        self.close()
        resolved_world = world_id or self.default_world_id
        resolved_task = task_id or self.default_task_id
        if not resolved_world or not resolved_task:
            raise ValueError("reset requires world_id and task_id, or defaults set in the constructor")

        self.spec = get_world_spec(resolved_world)
        self.task = get_task(self.spec.id, resolved_task)
        if self.reset_state:
            reset_world(self.spec.id, self.state_root)

        self.conn = connect_world(self.spec.id, self.state_root)
        tools_module = importlib.import_module(self.spec.tools_module)
        self.verifier_module = importlib.import_module(self.spec.verifier_module)
        self.recorder = ToolRecorder(self.conn, tools_module.TOOLS)
        self.before_snapshot = snapshot_database(self.conn)
        self.turns = 0
        self.done = False
        self.last_result = None
        return self._initial_observation(tools_module.TOOLS)

    def reset_gym(self, world_id: str | None = None, task_id: str | None = None) -> tuple[str, dict[str, Any]]:
        observation = self.reset(world_id, task_id)
        return observation, {"world": self.spec.id, "task_id": self.task["id"]}

    def step(self, action: str | dict[str, Any]) -> StepResult:
        self._require_active()
        if self.done:
            assert self.last_result is not None
            return self.last_result

        self.turns += 1
        try:
            parsed = parse_action(action)
        except ValueError as exc:
            observation = _json_observation(
                {
                    "error": "invalid_action",
                    "message": str(exc),
                    "expected": action_contract(),
                }
            )
            if self.turns >= self.max_turns:
                return self._finish("max_turns", prefix=observation)
            result = StepResult(observation=observation, reward=0.0, done=False, metadata={"error": "invalid_action"})
            self.last_result = result
            return result

        if parsed.get("action") == "done" or parsed.get("type") == "done":
            return self._finish("agent_done")

        tool_name = parsed.get("tool") or parsed.get("name")
        arguments = parsed.get("arguments") or {}
        if not isinstance(arguments, dict):
            observation = _json_observation(
                {
                    "error": "invalid_arguments",
                    "message": "Action arguments must be a JSON object.",
                }
            )
            if self.turns >= self.max_turns:
                return self._finish("max_turns", prefix=observation)
            result = StepResult(
                observation=observation,
                reward=0.0,
                done=False,
                metadata={"error": "invalid_arguments"},
            )
            self.last_result = result
            return result

        assert self.recorder is not None
        output = self.recorder.safe_call(str(tool_name), **arguments)
        call = self.recorder.calls[-1]
        observation = _json_observation(
            {
                "turn": self.turns,
                "tool": call["tool"],
                "status": call["status"],
                "output": output,
            }
        )
        if self.turns >= self.max_turns:
            return self._finish("max_turns", prefix=observation)

        result = StepResult(
            observation=observation,
            reward=0.0,
            done=False,
            metadata={"tool_status": call["status"], "turn": self.turns},
        )
        self.last_result = result
        return result

    def step_gym(self, action: str | dict[str, Any]) -> tuple[str, float, bool, bool, dict[str, Any]]:
        result = self.step(action)
        reason = result.metadata.get("termination_reason")
        terminated = result.done and reason != "max_turns"
        truncated = result.done and reason == "max_turns"
        return result.observation, result.reward, terminated, truncated, result.metadata

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
        self.conn = None
        self.recorder = None

    def _finish(self, termination_reason: str, prefix: str | None = None) -> StepResult:
        self._require_active()
        assert self.conn is not None
        assert self.recorder is not None
        assert self.spec is not None
        assert self.task is not None
        assert self.before_snapshot is not None

        after_snapshot = snapshot_database(self.conn)
        state_diff = diff_snapshots(self.before_snapshot, after_snapshot)
        verifier_result = self.verifier_module.verify(self.conn, self.task)
        generated_followups = []
        if not verifier_result["passed"]:
            generated_followups = generate_followups(self.spec.id, self.task, verifier_result)

        metadata = {
            "world": self.spec.id,
            "task_id": self.task["id"],
            "turns": self.turns,
            "termination_reason": termination_reason,
            "passed": verifier_result["passed"],
            "failure_type": verifier_result.get("failure_type"),
            "verifier": verifier_result,
            "tool_calls": self.recorder.calls,
            "state_diff": state_diff,
            "generated_followups": generated_followups,
        }
        payload = {
            "done": True,
            "termination_reason": termination_reason,
            "reward": verifier_result["reward"],
            "verifier": verifier_result,
            "state_diff_items": len(state_diff),
            "generated_followups": generated_followups,
        }
        observation = _json_observation(payload)
        if prefix:
            observation = f"{prefix}\n{observation}"

        result = StepResult(
            observation=observation,
            reward=float(verifier_result["reward"]),
            done=True,
            metadata=metadata,
        )
        self.done = True
        self.last_result = result
        self.close()
        return result

    def _initial_observation(self, registry: dict[str, Callable[..., dict[str, Any]]]) -> str:
        assert self.spec is not None
        assert self.task is not None
        return _json_observation(
            {
                "world": self.spec.id,
                "task_id": self.task["id"],
                "task_prompt": self.task["prompt"],
                "available_tools": tool_contract(registry),
                "action_contract": action_contract(),
                "reward_contract": "Intermediate reward is 0. Final reward comes from the deterministic verifier.",
            }
        )

    def _require_active(self) -> None:
        if self.spec is None or self.task is None:
            raise RuntimeError("Call reset before step")
        if self.conn is None and not self.done:
            raise RuntimeError("Environment connection is closed")


def parse_action(action: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(action, dict):
        payload = action
    else:
        text = action.strip()
        if text.upper() == "DONE":
            return {"action": "done"}
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Action must be JSON or DONE") from exc

    if not isinstance(payload, dict):
        raise ValueError("Action must decode to a JSON object")

    if "function" in payload and isinstance(payload["function"], dict):
        function = payload["function"]
        payload = {
            "tool": function.get("name"),
            "arguments": function.get("arguments") or {},
        }
    if isinstance(payload.get("arguments"), str):
        payload = dict(payload)
        payload["arguments"] = json.loads(payload["arguments"])
    return payload


def tool_contract(registry: dict[str, Callable[..., dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {name: _function_contract(function) for name, function in sorted(registry.items())}


def action_contract() -> dict[str, Any]:
    return {
        "tool_action": {"tool": "tool_name", "arguments": {"argument_name": "value"}},
        "done_action": {"action": "done"},
    }


def _function_contract(function: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    signature = inspect.signature(function)
    parameters = {}
    required = []
    for name, parameter in signature.parameters.items():
        if name == "conn":
            continue
        parameters[name] = {
            "required": parameter.default is inspect.Parameter.empty,
            "default": None if parameter.default is inspect.Parameter.empty else parameter.default,
        }
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return {"parameters": parameters, "required": required}


def _json_observation(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
