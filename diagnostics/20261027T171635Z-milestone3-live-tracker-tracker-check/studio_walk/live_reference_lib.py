"""A MotionLib stand-in that serves the reference walker's frames to the tracker environment.

The mimic environment asks its motion library for the reference at the current motion time and
one control step ahead. This facade answers those queries from the ``ReferenceWalker``: frames
are generated lazily and in order, each anchored to the character's actual heading, with
positions integrated from the previous reference frame. With the motion manager's
``realign_motion_with_humanoid_on_each_step`` enabled the environment re-anchors the reference's
planar position to the character every step, so the tracker always sees "one frame ahead of where
you are" and lag cannot accumulate. The virtual motion never ends.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

import torch

from protomotions.simulator.base_simulator.simulator_state import RobotState
from protomotions.utils.rotations import quat_to_exp_map

from studio_walk.reference_walker import ROOT, ReferencePose, ReferenceWalker, heading_of, quat_conj, quat_mul


def quat_angular_velocity(q_from: torch.Tensor, q_to: torch.Tensor, fps: float) -> torch.Tensor:
    """World-frame angular velocity taking ``q_from`` to ``q_to`` in one frame (quaternions x, y, z, w)."""
    delta = quat_mul(q_to, quat_conj(q_from))
    delta = torch.where(delta[..., 3:4] < 0, -delta, delta)
    sin_half = delta[..., :3].norm(dim=-1, keepdim=True)
    angle = 2.0 * torch.atan2(sin_half, delta[..., 3:4])
    axis = delta[..., :3] / sin_half.clamp(min=1e-8)
    return axis * angle * fps


class LiveReferenceLib:
    """Duck-typed replacement for ``MotionLib`` holding one endless virtual motion."""

    def __init__(self, base_lib, walker: ReferenceWalker, actual_state: Callable[[], RobotState], device, num_motion_slots: int):
        self._base = base_lib                      # anything not overridden here is answered by the real library
        self.config = base_lib.config
        self.device = device
        self.motion_file = "studio-reference-walker"
        self.walker = walker
        self.actual_state = actual_state
        self.fps = walker.fps
        self.dt = 1.0 / self.fps
        virtual_seconds = 1.0e6
        self.motion_lengths = torch.full((num_motion_slots,), virtual_seconds, device=device)
        self.motion_num_frames = torch.full((num_motion_slots,), int(virtual_seconds * self.fps), dtype=torch.long, device=device)
        self.motion_dt = torch.full((num_motion_slots,), self.dt, device=device)
        self.motion_weights = torch.ones(num_motion_slots, device=device)
        self.length_starts = torch.zeros(num_motion_slots, dtype=torch.long, device=device)
        self.motion_files = tuple(self.motion_file for _ in range(num_motion_slots))
        self.frames: dict[int, ReferencePose] = {}
        self.latest: Optional[int] = None
        self.generated = 0
        self.begin_session()

    def __getattr__(self, name):
        if name == "_base":
            raise AttributeError(name)
        return getattr(self._base, name)

    # ---- MotionLib surface used by the environment ------------------------------------------
    def num_motions(self) -> int:
        return int(self.motion_lengths.shape[0])

    def get_motion_length(self, motion_ids=None) -> torch.Tensor:
        return self.motion_lengths if motion_ids is None else self.motion_lengths[motion_ids]

    def get_motion_num_frames(self, motion_ids=None) -> torch.Tensor:
        return self.motion_num_frames if motion_ids is None else self.motion_num_frames[motion_ids]

    def get_motion_state(self, motion_ids: torch.Tensor, motion_times: torch.Tensor, joint_3d_format: str = "exp_map") -> RobotState:
        keys = [int(round(float(t) * self.fps)) for t in motion_times]
        for key in keys:
            self._ensure(key)
        poses = [self.frames[key] for key in keys]
        nxt = [self.frames.get(key + 1) for key in keys]
        prev = [self.frames.get(key - 1) for key in keys]
        pos = torch.stack([p.rigid_body_pos for p in poses])
        rot = torch.stack([p.rigid_body_rot for p in poses])
        vel, ang = [], []
        for p, n, q in zip(poses, nxt, prev):
            other, sign = (n, 1.0) if n is not None else (q, -1.0) if q is not None else (None, 0.0)
            if other is None:
                vel.append(torch.zeros_like(p.rigid_body_pos)); ang.append(torch.zeros_like(p.rigid_body_pos))
            else:
                vel.append(sign * (other.rigid_body_pos - p.rigid_body_pos) * self.fps)
                ang.append(quat_angular_velocity(p.rigid_body_rot, other.rigid_body_rot, self.fps) if sign > 0
                           else quat_angular_velocity(other.rigid_body_rot, p.rigid_body_rot, self.fps))
        local = torch.stack([p.local_rot for p in poses])
        dof_pos = quat_to_exp_map(local[:, 1:, :].reshape(-1, 4), w_last=True).reshape(len(poses), -1)
        return RobotState(rigid_body_pos=pos, rigid_body_rot=rot, rigid_body_vel=torch.stack(vel), rigid_body_ang_vel=torch.stack(ang),
                          dof_pos=dof_pos, dof_vel=torch.stack([p.dof_vel for p in poses]),
                          rigid_body_contacts=torch.stack([p.contacts for p in poses]), local_rigid_body_rot=local)

    # ---- session control ------------------------------------------------------------------
    def begin_session(self):
        """Start a fresh virtual motion: frame 0 is the idle pose at the origin, heading zero."""
        self.walker.reset()
        self.frames.clear()
        origin = torch.zeros(2, device=self.device)
        pose = self.walker.next_pose(origin, torch.zeros((), device=self.device))
        self.frames[0] = pose
        self.latest = 0

    def _ensure(self, key: int):
        if key in self.frames:
            return
        if self.latest is None or key < self.latest:
            raise RuntimeError(f"reference frame {key} requested after frame {self.latest}; call begin_session() on reset")
        state = self.actual_state()
        actual_xy = state.rigid_body_pos[0, ROOT, :2]
        yaw = heading_of(state.rigid_body_rot[0, ROOT])
        while self.latest < key:
            previous = self.frames[self.latest]
            pose = self.walker.next_pose(previous.root_xy, yaw, actual_xy=actual_xy)
            self.latest += 1
            self.frames[self.latest] = pose
            self.generated += 1
        for old in [k for k in self.frames if k < self.latest - 4]:
            del self.frames[old]

    @property
    def phase(self) -> str:
        return self.walker.phase
