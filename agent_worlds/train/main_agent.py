from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        import hydra
        import ray
        from omegaconf import DictConfig
        from skyrl_gym.envs import register
        from skyrl_train.entrypoints.main_base import BasePPOExp, validate_cfg
        from skyrl_train.utils import initialize_ray
    except ImportError as exc:
        raise SystemExit(
            "Install Ray/Hydra plus SkyRL before training. "
            'Start with: python -m pip install -e ".[train]"'
        ) from exc

    config_path = str(Path(__file__).resolve().parent / "confs")

    @ray.remote(num_cpus=1)
    def skyrl_entrypoint(cfg: DictConfig) -> None:
        register(
            id="agent_worlds",
            entry_point="agent_worlds.train.skyrl_env:SkyRLAgentEnv",
        )
        exp = BasePPOExp(cfg)
        exp.run()

    @hydra.main(config_path=config_path, config_name="base", version_base=None)
    def hydra_main(cfg: DictConfig) -> None:
        validate_cfg(cfg)
        initialize_ray(cfg)
        ray.get(skyrl_entrypoint.remote(cfg))

    hydra_main()


if __name__ == "__main__":
    main()
