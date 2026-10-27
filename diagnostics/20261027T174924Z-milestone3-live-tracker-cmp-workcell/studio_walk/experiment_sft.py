"""Supervised bootstrap of the walking adapter on reference clips (ProtoMotions GPC SFT).

Follows examples/experiments/gpc/sft_target_prior_peft.py at the pinned revision with
three recorded differences: the mimic lookahead steps come from the prior checkpoint's own
training configuration (the FSQ tracker it names is not shipped at this revision), the
motion library excludes floor-level clips and the reserved evaluation clips, and
inference overrides install the studio's scripted destination source.
"""
import argparse

from studio_walk import PRIOR_CHECKPOINT, TARGET_PROXIMITY_THRESHOLD
from studio_walk import experiment_common as common
from studio_walk.experiment_common import (  # noqa: F401  (experiment contract)
    motion_lib_config,
    scene_lib_config,
    terrain_config,
)

LOOKAHEAD_SECONDS_MIN = 1.0
LOOKAHEAD_SECONDS_MAX = 5.0
TARGET_JITTER_RADIUS = 0.5
PRIOR_TOP_P = 0.99


def additional_experiment_arguments(parser: argparse.ArgumentParser):
    common.add_prior_argument(parser)


def configure_robot_and_simulator(robot_cfg, simulator_cfg, args):
    robot_cfg.update_fields(contact_bodies=["all_left_foot_bodies", "all_right_foot_bodies"])


def env_config(robot_cfg, args):
    from protomotions.envs.action import make_pd_action_config
    from protomotions.envs.base_env.config import EnvConfig
    from protomotions.envs.component_factories import (
        max_coords_obs_factory,
        mimic_target_poses_max_coords_factory,
        target_obs_factory,
        target_reward_factory,
        tracking_error_term_factory,
    )
    from protomotions.envs.control.gpc_sft_reference_target_control import (
        GPCSFTReferenceTargetControlConfig,
    )
    from protomotions.envs.control.mimic_control import MimicControlConfig

    prior_checkpoint = getattr(args, "prior_checkpoint", PRIOR_CHECKPOINT)
    return EnvConfig(
        ref_contact_smooth_window=7,
        max_episode_length=256,
        reset_grace_period=2,
        ref_respawn_offset=0.0,
        control_components={
            "mimic": MimicControlConfig(
                bootstrap_on_episode_end=True,
                future_steps=common.prior_future_steps(prior_checkpoint),
            ),
            "target": GPCSFTReferenceTargetControlConfig(
                lookahead_seconds_min=LOOKAHEAD_SECONDS_MIN,
                lookahead_seconds_max=LOOKAHEAD_SECONDS_MAX,
                target_jitter_radius=TARGET_JITTER_RADIUS,
                tar_proximity_threshold=TARGET_PROXIMITY_THRESHOLD,
            ),
        },
        observation_components={
            "max_coords_obs": max_coords_obs_factory(),
            "task_obs": target_obs_factory(),
            "mimic_target_poses": mimic_target_poses_max_coords_factory(with_velocities=True),
        },
        reward_components={"target": target_reward_factory(weight=1.0)},
        termination_components={"tracking_error": tracking_error_term_factory(threshold=0.5)},
        action_config=make_pd_action_config(robot_cfg),
        motion_manager=common.motion_manager_config(init_start_prob=0.2),
    )


def agent_config(robot_config, env_config, args):
    from protomotions.agents.base_agent.config import OptimizerConfig
    from protomotions.agents.common.config import PretrainedModelConfig
    from protomotions.agents.evaluators.config import EvaluatorConfig
    from protomotions.agents.peft.prior_config import (
        DiscretePriorPEFTActorConfig,
        DiscretePriorPEFTConfig,
        DiscretePriorPEFTSFTAgentConfig,
        DiscretePriorPEFTSFTModelConfig,
    )

    prior_checkpoint = getattr(args, "prior_checkpoint", PRIOR_CHECKPOINT)
    return DiscretePriorPEFTSFTAgentConfig(
        pretrained_modules={"prior": PretrainedModelConfig(checkpoint_path=prior_checkpoint, module_path="")},
        model=DiscretePriorPEFTSFTModelConfig(
            actor=DiscretePriorPEFTActorConfig(
                in_keys=["task_obs"],
                peft=DiscretePriorPEFTConfig(
                    peft_type="dora", rank=32, alpha=64, temperature=1.0, top_p=0.9,
                    sampling_mode="prior_constraint", prior_top_p=PRIOR_TOP_P,
                    m_clamp=1.6, film_input_norm=True,
                ),
            ),
            actor_optimizer=OptimizerConfig(_target_="torch.optim.AdamW", lr=1e-4),
        ),
        batch_size=args.batch_size,
        training_max_steps=args.training_max_steps,
        num_steps=32,
        num_mini_epochs=1,
        normalize_rewards=False,
        gradient_clip_val=50.0,
        save_last_checkpoint_every=10,
        evaluator=EvaluatorConfig(eval_metrics_every=None),
    )


def apply_inference_overrides(robot_cfg, simulator_cfg, env_cfg, agent_cfg, terrain_cfg,
                              motion_lib_cfg, scene_lib_cfg, args):
    common.apply_studio_inference_overrides(env_cfg)
    env_cfg.observation_components.pop("mimic_target_poses", None)
