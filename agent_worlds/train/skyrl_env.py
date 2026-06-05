from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_worlds.rl.env import AgentTextEnv

try:  # pragma: no cover - exercised only when SkyRL is installed.
    from skyrl_gym.envs.base_text_env import BaseTextEnv, BaseTextEnvStepOutput

    SKYRL_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback is covered in local tests.
    SKYRL_AVAILABLE = False

    class BaseTextEnv:  # type: ignore[no-redef]
        def __init__(self) -> None:
            self.turns = 0

    @dataclass
    class BaseTextEnvStepOutput:  # type: ignore[no-redef]
        observations: list[dict[str, str]]
        reward: float
        done: bool
        metadata: dict[str, Any]


class SkyRLAgentEnv(BaseTextEnv):
    """SkyRL text environment wrapper for deterministic verifier-backed tasks."""

    def __init__(self, env_config: dict[str, Any] | None = None, extras: dict[str, Any] | None = None) -> None:
        super().__init__()
        env_config = env_config or {}
        extras = extras or {}
        extra_info = extras.get("extra_info") or {}
        max_turns = _coerce_int(
            extra_info.get("max_turns", extras.get("max_turns", env_config.get("max_turns", 16))),
            default=16,
        )
        state_root = extra_info.get("state_root") or env_config.get("state_root")
        self.world_id = extra_info.get("world") or extra_info.get("world_id") or env_config.get("world")
        self.task_id = extra_info.get("task_id") or env_config.get("task_id")
        if not self.world_id or not self.task_id:
            raise ValueError("SkyRLAgentEnv requires extra_info.world and extra_info.task_id")

        self._env = AgentTextEnv(
            world_id=str(self.world_id),
            task_id=str(self.task_id),
            state_root=Path(state_root) if state_root else None,
            max_turns=max_turns,
        )
        self._initialized = False
        self._last_observation = ""

    def reset(self) -> list[dict[str, str]]:
        self.turns = 0
        self._last_observation = self._env.reset()
        self._initialized = True
        return [{"role": "user", "content": self._last_observation}]

    def step(self, action: str) -> BaseTextEnvStepOutput:
        if not self._initialized:
            self.reset()

        result = self._env.step(action)
        self.turns += 1
        if result.done:
            self._initialized = False
        return BaseTextEnvStepOutput(
            observations=[{"role": "user", "content": result.observation}],
            reward=result.reward,
            done=result.done,
            metadata={
                "goal_reached": result.metadata.get("passed", False),
                "world": result.metadata.get("world", self.world_id),
                "task_id": result.metadata.get("task_id", self.task_id),
                "failure_type": result.metadata.get("failure_type"),
                "termination_reason": result.metadata.get("termination_reason"),
                "verifier": result.metadata.get("verifier"),
                "env_cleaned_up": result.done,
            },
        )


def skyrl_available() -> bool:
    return SKYRL_AVAILABLE


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
