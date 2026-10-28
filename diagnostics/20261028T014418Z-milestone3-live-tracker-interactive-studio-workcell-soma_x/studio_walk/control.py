"""Destination command sources for ProtoMotions' TargetControl.

``StudioRandomTargetCommandSource`` drives training: destinations 1-5 m away in a random
direction, occasional stand-still commands, timed destination changes and occasional
early redirections while walking. ``ScriptedTargetCommandSource`` is a programmatic
source for evaluation and live direction: targets are set or scheduled explicitly by the
studio, never sampled, and nothing is hidden by automatic resampling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import torch
from torch import Tensor

from protomotions.envs.control.target_control import (
    TargetCommandSource,
    TargetCommandSourceConfig,
)
from protomotions.utils.rotations import calc_heading_quat, quat_rotate


@dataclass
class StudioRandomTargetCommandSourceConfig(TargetCommandSourceConfig):
    """Training-time destination sampler with declared ranges."""

    _target_: str = "studio_walk.control.StudioRandomTargetCommandSource"
    tar_dist_min: float = 1.0
    tar_dist_max: float = 5.0
    tar_change_time_min: float = 6.0
    tar_change_time_max: float = 9.0
    stand_probability: float = 0.1
    redirect_probability: float = 0.3
    redirect_time_min: float = 1.5
    redirect_time_max: float = 5.0
    target_bounds: Optional[Tuple[float, float, float, float]] = None


class StudioRandomTargetCommandSource(TargetCommandSource):
    config: StudioRandomTargetCommandSourceConfig

    def __init__(self, config, control):
        super().__init__(config, control)
        self.config = config

    def reset(self, env_ids: Tensor) -> None:
        self._sample(env_ids, allow_redirect=True, episode_time=None)

    def step(self) -> None:
        control = self.control
        env = control.env
        elapsed = env.progress_buf * env.dt
        due = (elapsed >= control._tar_change_time).nonzero(as_tuple=False).flatten()
        if len(due) > 0:
            self._sample(due, allow_redirect=False, episode_time=elapsed[due])

    def _sample(self, env_ids: Tensor, allow_redirect: bool, episode_time: Optional[Tensor]) -> None:
        control = self.control
        env = control.env
        cfg = self.config
        device = env.device
        count = len(env_ids)
        state = env.simulator.get_robot_state(env_ids)
        anchor = env.robot_config.anchor_body_index
        root_pos = state.rigid_body_pos[:, anchor]
        root_rot = state.rigid_body_rot[:, anchor]

        dist = cfg.tar_dist_min + torch.rand(count, device=device) * (cfg.tar_dist_max - cfg.tar_dist_min)
        stand = torch.rand(count, device=device) < cfg.stand_probability
        dist = torch.where(stand, torch.zeros_like(dist), dist)
        angle = torch.rand(count, device=device) * 2.0 * torch.pi
        local = torch.zeros(count, 3, device=device)
        local[:, 0] = dist * torch.cos(angle)
        local[:, 1] = dist * torch.sin(angle)
        world = quat_rotate(calc_heading_quat(root_rot, w_last=True), local, w_last=True)
        target_xy = root_pos[:, :2] + world[:, :2]
        if cfg.target_bounds is not None:
            x_min, x_max, y_min, y_max = cfg.target_bounds
            target_xy[:, 0] = target_xy[:, 0].clamp(x_min, x_max)
            target_xy[:, 1] = target_xy[:, 1].clamp(y_min, y_max)
        control._tar_pos[env_ids, :2] = target_xy
        control._update_target_heights(env_ids)

        now = torch.zeros(count, device=device) if episode_time is None else episode_time
        redirect = torch.rand(count, device=device) < cfg.redirect_probability
        if not allow_redirect:
            redirect = torch.zeros_like(redirect)
        change_delay = cfg.tar_change_time_min + torch.rand(count, device=device) * (
            cfg.tar_change_time_max - cfg.tar_change_time_min)
        redirect_delay = cfg.redirect_time_min + torch.rand(count, device=device) * (
            cfg.redirect_time_max - cfg.redirect_time_min)
        control._tar_change_time[env_ids] = now + torch.where(redirect, redirect_delay, change_delay)


@dataclass
class ScriptedTargetCommandSourceConfig(TargetCommandSourceConfig):
    """Explicit destination control for evaluation and live direction."""

    _target_: str = "studio_walk.control.ScriptedTargetCommandSource"
    max_events: int = 8


class ScriptedTargetCommandSource(TargetCommandSource):
    config: ScriptedTargetCommandSourceConfig

    def __init__(self, config, control):
        super().__init__(config, control)
        self.config = config
        env = control.env
        self.num_envs = env.num_envs
        self.device = env.device
        slots = config.max_events
        self.event_time = torch.full((self.num_envs, slots), float("inf"), device=self.device)
        self.event_xy = torch.zeros(self.num_envs, slots, 2, device=self.device)
        self.event_pending = torch.zeros(self.num_envs, slots, dtype=torch.bool, device=self.device)
        self.applied_events = []

    def reset(self, env_ids: Tensor) -> None:
        """Hold position until the studio commands a destination."""
        control = self.control
        env = control.env
        state = env.simulator.get_robot_state(env_ids)
        anchor = env.robot_config.anchor_body_index
        control._tar_pos[env_ids] = state.rigid_body_pos[:, anchor]
        control._update_target_heights(env_ids)
        control._tar_change_time[env_ids] = float("inf")
        self.event_pending[env_ids] = False
        self.event_time[env_ids] = float("inf")

    def step(self) -> None:
        env = self.control.env
        elapsed = env.progress_buf * env.dt
        for slot in range(self.config.max_events):
            due = self.event_pending[:, slot] & (elapsed >= self.event_time[:, slot])
            if due.any():
                env_ids = due.nonzero(as_tuple=False).flatten()
                self.set_target_now(env_ids, self.event_xy[env_ids, slot])
                self.event_pending[env_ids, slot] = False
                self.applied_events.append({
                    "slot": slot,
                    "env_ids": env_ids.tolist(),
                    "step": env.progress_buf[env_ids].tolist(),
                })

    def set_target_now(self, env_ids: Tensor, target_xy: Tensor) -> None:
        control = self.control
        control._tar_pos[env_ids, :2] = target_xy.to(self.device)
        control._update_target_heights(env_ids)
        control._tar_change_time[env_ids] = float("inf")

    def hold_position(self, env_ids: Tensor) -> None:
        """Stop walking: the destination becomes the current pelvis position."""
        env = self.control.env
        state = env.simulator.get_robot_state(env_ids)
        anchor = env.robot_config.anchor_body_index
        self.set_target_now(env_ids, state.rigid_body_pos[:, anchor, :2])

    def schedule(self, env_ids: Tensor, slot: int, time_seconds: Tensor, target_xy: Tensor) -> None:
        self.event_time[env_ids, slot] = time_seconds.to(self.device)
        self.event_xy[env_ids, slot] = target_xy.to(self.device)
        self.event_pending[env_ids, slot] = True

    def targets(self) -> Tensor:
        return self.control._tar_pos.clone()


__all__ = [
    "StudioRandomTargetCommandSourceConfig",
    "StudioRandomTargetCommandSource",
    "ScriptedTargetCommandSourceConfig",
    "ScriptedTargetCommandSource",
]
