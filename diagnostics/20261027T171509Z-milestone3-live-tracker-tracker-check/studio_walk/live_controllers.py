"""Controllers the live-direction worker can drive: the learned walking adapter or the
tracker-driven walker. Both expose the same small surface so the session loop, commands,
recording and evidence stay identical.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import torch


def sha256_of(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class AdapterController:
    """GPC prior + DoRA walking adapter (Milestone 3 training output)."""
    name = "adapter"

    def __init__(self, args, device, fabric, app, motion_file: str):
        from protomotions.simulator.base_simulator.utils import convert_friction_for_simulator
        from protomotions.utils.component_builder import build_all_components
        from protomotions.utils.hydra_replacement import get_class
        from studio_walk.control import ScriptedTargetCommandSource
        from studio_walk.experiment_common import apply_studio_inference_overrides

        self.device = device
        self.checkpoint = args.adapter_checkpoint
        configs = torch.load(self.checkpoint.parent / "resolved_configs_inference.pt", map_location="cpu", weights_only=False)
        robot, sim_cfg, env_cfg = configs["robot"], configs["simulator"], configs["env"]
        apply_studio_inference_overrides(env_cfg)
        sim_cfg.num_envs, sim_cfg.headless, sim_cfg.w_last = 1, True, True
        configs["motion_lib"].motion_file = motion_file
        configs["motion_lib"].motion_file_shard_indices = None
        configs["agent"].pretrained_modules["prior"].checkpoint_path = str(args.prior_checkpoint)
        terrain_cfg, sim_cfg = convert_friction_for_simulator(configs["terrain"], sim_cfg)
        configs["terrain"], configs["simulator"] = terrain_cfg, sim_cfg
        self.configs, self.robot = configs, robot
        components = build_all_components(terrain_cfg, configs["scene_lib"], configs["motion_lib"], sim_cfg, robot, device, simulation_app=app)
        self.sim = components["simulator"]
        self.env = get_class(env_cfg._target_)(config=env_cfg, robot_config=robot, device=device, terrain=components["terrain"],
                                               scene_lib=components["scene_lib"], motion_lib=components["motion_lib"], simulator=self.sim)
        self.source = self.env.control_manager.components["target"].command_source
        assert isinstance(self.source, ScriptedTargetCommandSource)
        self.agent = get_class(configs["agent"]._target_)(config=configs["agent"], env=self.env, fabric=fabric, root_dir=args.output / "upstream")
        self.agent.setup()
        self.agent.load(self.checkpoint, load_env=False, load_training_state=False)
        self.agent.eval()
        self.contract = {"controller": self.name, "adapter_checkpoint": str(self.checkpoint), "adapter_sha256": sha256_of(self.checkpoint),
                         "prior_checkpoint": str(args.prior_checkpoint), "prior_sha256": sha256_of(args.prior_checkpoint)}

    def act(self, obs, step):
        self.agent.pre_collect_step(step)
        td = self.agent.obs_dict_to_tensordict(self.agent.add_agent_info_to_obs(obs))
        out = self.agent.model(td)
        return out["mean_action"] if "mean_action" in out.keys() else out["action"]

    def reset(self, env_ids, start_motion_id: int):
        self.env.motion_manager.motion_ids[:] = start_motion_id
        self.env.motion_manager.motion_times[:] = 0.0

    def after_reset(self, env_ids):
        if hasattr(self.agent.model, "reset_rollout_context"):
            self.agent.model.reset_rollout_context(env_ids=env_ids)
        self.source.hold_position(env_ids)

    def set_destination(self, env_ids, world_xy: torch.Tensor):
        self.source.set_target_now(env_ids, world_xy.unsqueeze(0))

    def hold(self, env_ids):
        self.source.hold_position(env_ids)

    def target_xy(self) -> torch.Tensor:
        return self.env.control_manager.components["target"]._tar_pos[0, :2]

    def phase(self) -> Optional[str]:
        return None


class TrackerController:
    """Milestone 1 motion tracker following a reference composed on the fly from licensed clips."""
    name = "tracker"

    def __init__(self, args, device, fabric, app, motion_file: str):
        from protomotions.simulator.base_simulator.utils import convert_friction_for_simulator
        from protomotions.utils.component_builder import build_all_components
        from protomotions.utils.hydra_replacement import get_class
        from studio_walk.live_reference_lib import LiveReferenceLib
        from studio_walk.reference_walker import build_default_walker

        self.device = device
        self.checkpoint = args.tracker_checkpoint
        configs = torch.load(self.checkpoint.parent / "resolved_configs_inference.pt", map_location="cpu", weights_only=False)
        robot, sim_cfg, env_cfg = configs["robot"], configs["simulator"], configs["env"]
        if robot.contact_bodies is None:
            robot.contact_bodies = ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
        sim_cfg.num_envs, sim_cfg.headless, sim_cfg.w_last = 1, True, True
        env_cfg.termination_components = {}
        env_cfg.max_episode_length = 1_000_000
        env_cfg.motion_manager.realign_motion_with_humanoid_on_each_step = True
        env_cfg.motion_manager.init_start_prob = 1.0
        env_cfg.motion_manager.resample_on_reset = False
        configs["motion_lib"].motion_file = motion_file
        configs["motion_lib"].motion_file_shard_indices = None
        terrain_cfg, sim_cfg = convert_friction_for_simulator(configs["terrain"], sim_cfg)
        configs["terrain"], configs["simulator"] = terrain_cfg, sim_cfg
        self.configs, self.robot = configs, robot
        components = build_all_components(terrain_cfg, configs["scene_lib"], configs["motion_lib"], sim_cfg, robot, device, simulation_app=app)
        self.sim = components["simulator"]
        self.env = get_class(env_cfg._target_)(config=env_cfg, robot_config=robot, device=device, terrain=components["terrain"],
                                               scene_lib=components["scene_lib"], motion_lib=components["motion_lib"], simulator=self.sim)
        base_lib = components["motion_lib"]
        self.walker, self.segments = build_default_walker(base_lib, walk_clip=args.walk_clip, stop_clip=args.stop_clip, idle_clip=args.idle_clip)
        self.reference = LiveReferenceLib(base_lib, self.walker, lambda: self.sim.get_robot_state(), device, base_lib.num_motions())
        self.env.motion_lib = self.reference
        self.env.motion_manager.motion_lib = self.reference
        self.agent = get_class(configs["agent"]._target_)(config=configs["agent"], env=self.env, fabric=fabric, root_dir=args.output / "upstream")
        self.agent.setup()
        self.agent.load(self.checkpoint, load_env=False, load_training_state=False)
        self.agent.eval()
        self.destination: Optional[torch.Tensor] = None
        self.contract = {"controller": self.name, "tracker_checkpoint": str(self.checkpoint), "tracker_sha256": sha256_of(self.checkpoint),
                         "motion_file": motion_file, "motion_file_sha256": sha256_of(Path(motion_file)), "segments": self.segments,
                         "reference": "composed on the fly from clip segments; closed-loop heading, planar realignment every step",
                         "learning": False}

    def act(self, obs, step):
        if hasattr(self.agent, "pre_collect_step"):
            self.agent.pre_collect_step(step)
        td = self.agent.obs_dict_to_tensordict(self.agent.add_agent_info_to_obs(obs))
        out = self.agent.model(td)
        return out["mean_action"] if "mean_action" in out.keys() else out["action"]

    def reset(self, env_ids, start_motion_id: int):
        self.reference.begin_session()
        self.destination = None
        self.env.motion_manager.motion_ids[:] = 0
        self.env.motion_manager.motion_times[:] = 0.0

    def after_reset(self, env_ids):
        if hasattr(self.agent.model, "reset_rollout_context"):
            self.agent.model.reset_rollout_context(env_ids=env_ids)

    def set_destination(self, env_ids, world_xy: torch.Tensor):
        self.destination = world_xy.clone()
        self.walker.set_destination(world_xy)

    def hold(self, env_ids):
        self.destination = None
        self.walker.request_stop()

    def target_xy(self) -> torch.Tensor:
        if self.destination is not None:
            return self.destination
        return self.sim.get_robot_state().rigid_body_pos[0, 0, :2]

    def phase(self) -> Optional[str]:
        return self.walker.phase


def build_controller(kind: str, args, device, fabric, app, motion_file: str):
    if kind == "adapter":
        return AdapterController(args, device, fabric, app, motion_file)
    if kind == "tracker":
        return TrackerController(args, device, fabric, app, motion_file)
    raise ValueError(kind)
