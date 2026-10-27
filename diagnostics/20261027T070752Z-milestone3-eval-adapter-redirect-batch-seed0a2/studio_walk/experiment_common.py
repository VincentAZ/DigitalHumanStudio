"""Shared configuration builders for the Milestone 3 SFT and RLFT experiments."""
from __future__ import annotations

import argparse

from studio_walk import (
    PRIOR_CHECKPOINT,
    SOMA_FORWARD_AXIS_XY,
    TARGET_PROXIMITY_THRESHOLD,
    TRAINING_EXCLUDED_MOTION_IDS,
)

FRICTION_RANGE = (0.5, 1.25)
FRICTION_BUCKETS = 64
WALKING_EPISODE_STEPS = 450  # 15 s at 30 Hz control


def add_prior_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prior-checkpoint", default=PRIOR_CHECKPOINT)


def add_disturbance_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--push-max-velocity", type=float, default=0.0,
                        help="Horizontal root velocity impulse bound in m/s (0 disables pushes).")
    parser.add_argument("--push-interval-min", type=float, default=3.0)
    parser.add_argument("--push-interval-max", type=float, default=6.0)
    parser.add_argument("--friction-randomization", type=int, default=1,
                        help="1 enables robot contact friction randomization within FRICTION_RANGE.")


def configure_contact_and_randomization(robot_cfg, simulator_cfg, args) -> None:
    from protomotions.simulator.base_simulator.config import (
        DomainRandomizationConfig,
        FrictionDomainRandomizationConfig,
        PushDomainRandomizationConfig,
    )

    robot_cfg.update_fields(contact_bodies=["all_left_foot_bodies", "all_right_foot_bodies"])
    friction = None
    if int(getattr(args, "friction_randomization", 0)) == 1:
        friction = FrictionDomainRandomizationConfig(
            num_buckets=FRICTION_BUCKETS,
            static_friction_range=FRICTION_RANGE,
            dynamic_friction_range=FRICTION_RANGE,
            restitution_range=(0.0, 0.0),
            body_names=[".*"],
        )
    push = None
    push_max = float(getattr(args, "push_max_velocity", 0.0))
    if push_max > 0.0:
        push = PushDomainRandomizationConfig(
            push_interval_range=(float(args.push_interval_min), float(args.push_interval_max)),
            max_linear_velocity=(push_max, push_max, 0.0),
            max_angular_velocity=(0.0, 0.0, 0.0),
        )
    if friction is not None or push is not None:
        simulator_cfg.domain_randomization = DomainRandomizationConfig(friction=friction, push=push)


def prior_future_steps(prior_checkpoint: str):
    """Lookahead steps the prior's embedded target encoder was trained with."""
    from protomotions.utils.config_utils import load_resolved_configs_from_checkpoint

    resolved = load_resolved_configs_from_checkpoint(prior_checkpoint, prefer_inference=False)
    mimic = resolved["env"].control_components.get("mimic")
    if mimic is None:
        raise ValueError(f"Prior checkpoint {prior_checkpoint} has no mimic control configuration")
    return list(mimic.future_steps)


def terrain_config(args):
    from protomotions.components.terrains.config import TerrainConfig

    return TerrainConfig()


def scene_lib_config(args):
    from protomotions.components.scene_lib import SceneLibConfig

    return SceneLibConfig(scene_file=getattr(args, "scenes_file", None))


def motion_lib_config(args):
    from protomotions.components.motion_lib import MotionLibConfig

    return MotionLibConfig(motion_file=args.motion_file)


def motion_manager_config(init_start_prob: float = 0.2):
    from protomotions.envs.motion_manager.config import MimicMotionManagerConfig

    return MimicMotionManagerConfig(
        init_start_prob=init_start_prob,
        resample_on_reset=True,
        exclude_motion_ids=list(TRAINING_EXCLUDED_MOTION_IDS),
    )


# Training attempt 2 (2026-10-27): attempt 1 reached 98/100 destinations but held still in only 8/100
# trials because exp(-3 v^2) still pays 0.93 at the 0.15 m/s gate speed. These scales make the
# stillness terms discriminate at the gate: exp(-40 v^2) is 0.41 at 0.15 m/s and 0.90 at 0.05 m/s.
STILLNESS_SCALE = 40.0
YAW_STILLNESS_SCALE = 2.0


def walking_reward_components():
    from protomotions.envs.component_factories import target_reward_factory
    from protomotions.envs.context_views import EnvContext
    from protomotions.envs.mdp_component import MdpComponent
    from studio_walk import kernels

    target_vars = {
        "root_pos": EnvContext.current.anchor_pos,
        "tar_pos": EnvContext.target.tar_pos,
        "tar_proximity_threshold": EnvContext.target.tar_proximity_threshold,
    }
    return {
        "target": target_reward_factory(weight=1.0, pos_err_scale=0.42),
        "progress": MdpComponent(
            compute_func=kernels.compute_progress_velocity_rew,
            dynamic_vars={**target_vars, "root_vel": EnvContext.current.anchor_vel},
            static_params={"weight": 0.5, "target_speed": 1.2, "slow_down_seconds": 1.0,
                           "still_scale": STILLNESS_SCALE},
        ),
        "standing": MdpComponent(
            compute_func=kernels.compute_standing_rew,
            dynamic_vars={**target_vars, "root_vel": EnvContext.current.anchor_vel,
                          "root_ang_vel": EnvContext.current.anchor_ang_vel},
            static_params={"weight": 0.5, "lin_scale": STILLNESS_SCALE, "ang_scale": YAW_STILLNESS_SCALE},
        ),
        "upright": MdpComponent(
            compute_func=kernels.compute_upright_rew,
            dynamic_vars={"root_pos": EnvContext.current.anchor_pos,
                          "root_rot": EnvContext.current.anchor_rot,
                          "ground_heights": EnvContext.ground_heights},
            static_params={"weight": 0.2, "standing_height": 0.85},
        ),
        "facing": MdpComponent(
            compute_func=kernels.compute_facing_rew,
            dynamic_vars={**target_vars, "root_rot": EnvContext.current.anchor_rot},
            static_params={"weight": 0.2, "forward_x": SOMA_FORWARD_AXIS_XY[0],
                           "forward_y": SOMA_FORWARD_AXIS_XY[1]},
        ),
    }


def fall_termination_component():
    from protomotions.envs.context_views import EnvContext
    from protomotions.envs.mdp_component import MdpComponent
    from studio_walk import kernels

    return MdpComponent(
        compute_func=kernels.compute_fall_term,
        dynamic_vars={
            "root_pos": EnvContext.current.anchor_pos,
            "root_rot": EnvContext.current.anchor_rot,
            "ground_heights": EnvContext.ground_heights,
            "progress_buf": EnvContext.progress_buf,
        },
        static_params={"min_root_height": 0.5, "min_up_z": 0.3, "grace_steps": 5},
    )


def peft_actor_config(args, sampling_kwargs: dict):
    from protomotions.agents.peft.prior_config import (
        DiscretePriorPEFTActorConfig,
        DiscretePriorPEFTConfig,
    )

    return DiscretePriorPEFTActorConfig(
        in_keys=["task_obs"],
        peft=DiscretePriorPEFTConfig(
            peft_type="dora",
            rank=32,
            alpha=64,
            temperature=1.0,
            film_input_norm=True,
            **sampling_kwargs,
        ),
    )


def peft_sampling_kwargs(mode: str) -> dict:
    if mode == "prior_constraint":
        return {"sampling_mode": "prior_constraint", "top_p": 1.0, "prior_top_p": 0.9, "kl_coeff": 0.0}
    if mode == "nucleus":
        return {"sampling_mode": "nucleus", "top_p": 0.9, "prior_top_p": 1.0, "kl_coeff": 0.1}
    raise ValueError(f"Unknown PEFT sampling mode {mode}")


def target_control_training_config():
    from protomotions.envs.control.target_control import TargetControlConfig
    from studio_walk.control import StudioRandomTargetCommandSourceConfig

    return TargetControlConfig(
        command_source=StudioRandomTargetCommandSourceConfig(
            tar_dist_min=1.0, tar_dist_max=5.0,
            tar_change_time_min=6.0, tar_change_time_max=9.0,
            stand_probability=0.1, redirect_probability=0.3,
            redirect_time_min=1.5, redirect_time_max=5.0,
        ),
        tar_proximity_threshold=TARGET_PROXIMITY_THRESHOLD,
        enable_fall_termination=False,
        enable_gap_termination=False,
        enable_stuck_termination=False,
    )


def target_control_scripted_config():
    from protomotions.envs.control.target_control import TargetControlConfig
    from studio_walk.control import ScriptedTargetCommandSourceConfig

    return TargetControlConfig(
        command_source=ScriptedTargetCommandSourceConfig(),
        tar_proximity_threshold=TARGET_PROXIMITY_THRESHOLD,
        enable_fall_termination=False,
        enable_gap_termination=False,
        enable_stuck_termination=False,
    )


def apply_studio_inference_overrides(env_cfg) -> None:
    """Evaluation and live sessions never terminate or resample on their own."""
    env_cfg.termination_components = {}
    env_cfg.max_episode_length = 1_000_000
    env_cfg.motion_manager.resample_on_reset = True
    env_cfg.motion_manager.init_start_prob = 1.0
    env_cfg.control_components = {"target": target_control_scripted_config()}
