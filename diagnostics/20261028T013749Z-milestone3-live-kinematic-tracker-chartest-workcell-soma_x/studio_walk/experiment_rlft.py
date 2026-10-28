"""PPO fine-tuning of the walking adapter for destination walking (ProtoMotions GPC RLFT).

Starts from examples/experiments/gpc/target_prior_peft.py at the pinned revision and adds
the Milestone 3 objectives: destinations 1-5 m away with timed changes and early
redirections, stand-still commands, explicit slowing/standing, upright and facing rewards,
a height/tilt fall termination, 15 s episodes, robot contact friction randomization, and
optional horizontal push disturbances for the second training stage.
"""
import argparse

from studio_walk import PRIOR_CHECKPOINT
from studio_walk import experiment_common as common
from studio_walk.experiment_common import (  # noqa: F401  (experiment contract)
    motion_lib_config,
    scene_lib_config,
    terrain_config,
)


def additional_experiment_arguments(parser: argparse.ArgumentParser):
    common.add_prior_argument(parser)
    common.add_disturbance_arguments(parser)
    parser.add_argument("--peft-sampling-mode", choices=("prior_constraint", "nucleus"),
                        default="prior_constraint")


def configure_robot_and_simulator(robot_cfg, simulator_cfg, args):
    common.configure_contact_and_randomization(robot_cfg, simulator_cfg, args)


def env_config(robot_cfg, args):
    from protomotions.envs.action import make_pd_action_config
    from protomotions.envs.base_env.config import EnvConfig
    from protomotions.envs.component_factories import (
        max_coords_obs_factory,
        target_obs_factory,
    )

    return EnvConfig(
        ref_contact_smooth_window=7,
        max_episode_length=common.WALKING_EPISODE_STEPS,
        reset_grace_period=5,
        ref_respawn_offset=0.0,
        control_components={"target": common.target_control_training_config()},
        observation_components={
            "max_coords_obs": max_coords_obs_factory(),
            "task_obs": target_obs_factory(),
        },
        reward_components=common.walking_reward_components(),
        termination_components={"fall": common.fall_termination_component()},
        action_config=make_pd_action_config(robot_cfg),
        motion_manager=common.motion_manager_config(init_start_prob=0.2),
    )


def agent_config(robot_config, env_config, args):
    from protomotions.agents.base_agent.config import OptimizerConfig
    from protomotions.agents.common.config import (
        MLPLayerConfig,
        MLPWithConcatConfig,
        PretrainedModelConfig,
    )
    from protomotions.agents.evaluators.config import EvaluatorConfig
    from protomotions.agents.peft.prior_config import (
        DiscretePriorPEFTRLFTAgentConfig,
        DiscretePriorPEFTRLFTModelConfig,
    )

    prior_checkpoint = getattr(args, "prior_checkpoint", PRIOR_CHECKPOINT)
    sampling = common.peft_sampling_kwargs(getattr(args, "peft_sampling_mode", "prior_constraint"))
    return DiscretePriorPEFTRLFTAgentConfig(
        pretrained_modules={"prior": PretrainedModelConfig(checkpoint_path=prior_checkpoint, module_path="")},
        e_clip=0.2,
        entropy_coef=0.0,
        tau=0.95,
        model=DiscretePriorPEFTRLFTModelConfig(
            actor=common.peft_actor_config(args, sampling),
            critic=MLPWithConcatConfig(
                in_keys=["max_coords_obs", "task_obs"],
                out_keys=["value"],
                normalize_obs=True,
                norm_clamp_value=10,
                num_out=1,
                layers=[MLPLayerConfig(units=1024, activation="relu") for _ in range(4)],
            ),
            actor_optimizer=OptimizerConfig(_target_="torch.optim.AdamW", lr=1e-4),
            critic_optimizer=OptimizerConfig(_target_="torch.optim.AdamW", lr=1e-4),
        ),
        batch_size=args.batch_size,
        training_max_steps=args.training_max_steps,
        num_steps=32,
        num_mini_epochs=2,
        normalize_rewards=True,
        gradient_clip_val=0.5,
        save_last_checkpoint_every=10,
        save_epoch_checkpoint_every=250,
        evaluator=EvaluatorConfig(eval_metrics_every=None),
    )


def apply_inference_overrides(robot_cfg, simulator_cfg, env_cfg, agent_cfg, terrain_cfg,
                              motion_lib_cfg, scene_lib_cfg, args):
    common.apply_studio_inference_overrides(env_cfg)
