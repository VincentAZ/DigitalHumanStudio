"""Tracker-driven walking: compose a kinematic reference from licensed clips and steer it to a destination.

The pretrained Milestone 1 tracker follows whatever reference frame it is shown next. This module
builds that reference on the fly from three pieces of the pinned clip set: a looped walk cycle, a
walk-to-stand transition and a standing idle loop. The root path is steered toward the current
destination; everything else (local joint rotations, DOF positions, contacts) is the clip's own
motion, so the result stays physically plausible for the tracker. No learning is involved.

Conventions follow the pinned motion files: quaternions are (x, y, z, w) (``w_last``), bodies are
in the robot's common ordering with the pelvis (``Hips``) first, and frames are 30 Hz.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import torch

ROOT = 0


# ---------------------------------------------------------------- quaternion helpers (x, y, z, w)
def quat_mul(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    ax, ay, az, aw = a.unbind(-1)
    bx, by, bz, bw = b.unbind(-1)
    return torch.stack([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz], dim=-1)


def quat_conj(q: torch.Tensor) -> torch.Tensor:
    return torch.cat([-q[..., :3], q[..., 3:]], dim=-1)


def quat_rotate(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    xyz, w = q[..., :3], q[..., 3:4]
    t = 2.0 * torch.cross(xyz, v, dim=-1)
    return v + w * t + torch.cross(xyz, t, dim=-1)


def yaw_quat(yaw: torch.Tensor) -> torch.Tensor:
    half = yaw * 0.5
    zeros = torch.zeros_like(half)
    return torch.stack([zeros, zeros, torch.sin(half), torch.cos(half)], dim=-1)


def heading_of(q: torch.Tensor) -> torch.Tensor:
    """Yaw of the body's x axis projected on the ground."""
    forward = quat_rotate(q, torch.tensor([1.0, 0.0, 0.0], device=q.device, dtype=q.dtype).expand(q.shape[:-1] + (3,)))
    return torch.atan2(forward[..., 1], forward[..., 0])


def wrap_angle(a: torch.Tensor) -> torch.Tensor:
    return torch.remainder(a + math.pi, 2 * math.pi) - math.pi


def quat_slerp(a: torch.Tensor, b: torch.Tensor, t: float) -> torch.Tensor:
    dot = (a * b).sum(-1, keepdim=True)
    b = torch.where(dot < 0, -b, b)
    dot = dot.abs().clamp(max=1.0)
    theta = torch.acos(dot)
    sin_theta = torch.sin(theta)
    near = sin_theta < 1e-4
    wa = torch.where(near, 1.0 - t, torch.sin((1.0 - t) * theta) / sin_theta.clamp(min=1e-8))
    wb = torch.where(near, torch.full_like(wa, t), torch.sin(t * theta) / sin_theta.clamp(min=1e-8))
    out = wa * a + wb * b
    return out / out.norm(dim=-1, keepdim=True)


# ---------------------------------------------------------------- clip segments
@dataclass
class Segment:
    """Frames of one clip expressed relative to the root's ground pose at every frame.

    ``rel_pos``/``rel_rot`` are body poses in the frame of the root's planar position and heading
    (root height is kept). ``step_forward``/``step_lateral``/``step_yaw`` are the root's per-frame
    planar displacement (in the previous frame's heading frame) and heading change.
    """
    name: str
    rel_pos: torch.Tensor      # (F, B, 3)
    rel_rot: torch.Tensor      # (F, B, 4) global rotations with root heading removed
    local_rot: torch.Tensor    # (F, B, 4)
    dof_pos: torch.Tensor      # (F, D)
    dof_vel: torch.Tensor      # (F, D)
    contacts: torch.Tensor     # (F, B)
    step_forward: torch.Tensor # (F,)
    step_lateral: torch.Tensor # (F,)
    step_yaw: torch.Tensor     # (F,)
    fps: float = 30.0

    @property
    def frames(self) -> int:
        return int(self.rel_pos.shape[0])

    @property
    def mean_speed(self) -> float:
        return float((self.step_forward.pow(2) + self.step_lateral.pow(2)).sqrt().mean() * self.fps)


def clip_frames(lib, motion_id: int) -> dict:
    """Raw frames of one motion from a loaded MotionLib (tensors on the library's device)."""
    start = int(lib.length_starts[motion_id])
    count = int(lib.motion_num_frames[motion_id])
    sl = slice(start, start + count)
    return {"gts": lib.gts[sl], "grs": lib.grs[sl], "lrs": lib.lrs[sl], "dps": lib.dps[sl], "dvs": lib.dvs[sl],
            "contacts": lib.contacts[sl], "fps": 1.0 / float(lib.motion_dt[motion_id]), "name": str(lib.motion_files[motion_id])}


def make_segment(frames: dict, start: int, end: int, name: str) -> Segment:
    gts, grs = frames["gts"][start:end], frames["grs"][start:end]
    root_xy = gts[:, ROOT, :2]
    yaw = heading_of(grs[:, ROOT])
    inv = yaw_quat(-yaw)                                        # (F, 4)
    rel = gts.clone()
    rel[:, :, :2] = gts[:, :, :2] - root_xy[:, None, :]
    inv_b = inv[:, None, :].expand(grs.shape)
    rel_pos = quat_rotate(inv_b, rel)
    rel_rot = quat_mul(inv_b, grs)
    delta = root_xy[1:] - root_xy[:-1]
    prev_inv = yaw_quat(-yaw[:-1])
    local_delta = quat_rotate(prev_inv, torch.cat([delta, torch.zeros_like(delta[:, :1])], dim=-1))
    step_forward = torch.cat([local_delta[:1, 0] * 0, local_delta[:, 0]])
    step_lateral = torch.cat([local_delta[:1, 1] * 0, local_delta[:, 1]])
    step_yaw = torch.cat([yaw[:1] * 0, wrap_angle(yaw[1:] - yaw[:-1])])
    return Segment(name=name, rel_pos=rel_pos, rel_rot=rel_rot, local_rot=frames["lrs"][start:end],
                   dof_pos=frames["dps"][start:end], dof_vel=frames["dvs"][start:end], contacts=frames["contacts"][start:end],
                   step_forward=step_forward, step_lateral=step_lateral, step_yaw=step_yaw, fps=frames["fps"])


def pose_distance(a: Segment, i: int, b: Segment, j: int) -> float:
    """Body-position distance between two root-relative frames (metres, mean over bodies)."""
    return float((a.rel_pos[i] - b.rel_pos[j]).norm(dim=-1).mean())


def find_walk_cycle(frames: dict, min_period: int = 20, max_period: int = 60, min_speed: float = 0.4,
                    search_start: int = 0) -> tuple[int, int, float]:
    """Pick (start, period) of the best-closing gait cycle in a clip's steady walking part."""
    full = make_segment(frames, 0, frames["gts"].shape[0], "full")
    speed = (full.step_forward.pow(2) + full.step_lateral.pow(2)).sqrt() * full.fps
    best = None
    count = full.frames
    for start in range(search_start, count - min_period):
        if float(speed[start:start + min_period].mean()) < min_speed:
            continue
        for period in range(min_period, max_period + 1):
            end = start + period
            if end >= count:
                break
            if float(speed[start:end].min()) < 0.2:
                continue
            closing = pose_distance(full, start, full, end)
            closing += 0.5 * float((full.dof_pos[start] - full.dof_pos[end]).abs().mean())
            if best is None or closing < best[2]:
                best = (start, period, closing)
    if best is None:
        raise ValueError("no walking cycle found")
    return best


def find_stop(frames: dict, still_speed: float = 0.15, hold_frames: int = 30) -> int:
    """First frame from which the root stays below ``still_speed`` for ``hold_frames`` frames."""
    full = make_segment(frames, 0, frames["gts"].shape[0], "full")
    speed = (full.step_forward.pow(2) + full.step_lateral.pow(2)).sqrt() * full.fps
    for i in range(full.frames - hold_frames):
        if float(speed[i:i + hold_frames].max()) < still_speed:
            return i
    raise ValueError("no still run found")


# ---------------------------------------------------------------- composer
@dataclass
class ReferencePose:
    rigid_body_pos: torch.Tensor   # (B, 3)
    rigid_body_rot: torch.Tensor   # (B, 4)
    local_rot: torch.Tensor        # (B, 4)
    dof_pos: torch.Tensor          # (D,)
    dof_vel: torch.Tensor          # (D,)
    contacts: torch.Tensor         # (B,)
    phase: str
    root_xy: torch.Tensor
    yaw: torch.Tensor


@dataclass
class ReferenceWalker:
    """Closed-loop kinematic reference: every control step the next frame is anchored to the
    character's actual planar root pose and heading, so lag never accumulates, and the walk cycle
    phase advances by exactly one frame. Phases: ``idle`` → ``walk`` → ``stop`` → ``idle``."""
    walk: Segment
    stop: Segment
    idle: Segment
    arrival_radius: float = 0.3
    slow_radius: float = 1.2
    turn_rate: float = math.radians(120.0)        # rad/s, maximum heading change of the reference
    blend_frames: int = 8
    travel_angle: float = 0.0                     # direction the walk cycle travels, in the heading frame
    phase: str = "idle"
    frame: int = 0
    destination: Optional[torch.Tensor] = None
    previous: Optional[ReferencePose] = None
    blend_from: Optional[ReferencePose] = None
    blend_left: int = 0
    history: list = field(default_factory=list)

    @property
    def fps(self) -> float:
        return self.walk.fps

    def __post_init__(self):
        self.travel_angle = math.atan2(float(self.walk.step_lateral.sum()), float(self.walk.step_forward.sum()))

    def reset(self):
        self.phase, self.frame, self.destination = "idle", 0, None
        self.previous, self.blend_from, self.blend_left = None, None, 0
        self.history.clear()

    def set_destination(self, xy: torch.Tensor):
        self.destination = xy.clone()
        if self.phase != "walk":
            self._enter("walk", 0)

    def request_stop(self):
        self.destination = None
        if self.phase == "walk":
            self._enter("stop", 0)

    def _enter(self, phase: str, frame: int):
        if self.previous is not None:
            self.blend_from, self.blend_left = self.previous, self.blend_frames
        self.phase, self.frame = phase, frame

    def _segment(self) -> Segment:
        return {"walk": self.walk, "stop": self.stop, "idle": self.idle}[self.phase]

    def _advance(self, distance: float):
        """Advance phase/frame for the next frame, deciding transitions from the current distance."""
        if self.phase == "walk":
            if self.destination is not None and distance <= self.arrival_radius:
                self._enter("stop", 0)
                return
            self.frame = (self.frame + 1) % self.walk.frames
        elif self.phase == "stop":
            self.frame += 1
            if self.frame >= self.stop.frames:
                self._enter("idle", 0)
        else:
            self.frame = (self.frame + 1) % self.idle.frames

    def next_pose(self, root_xy: torch.Tensor, yaw: torch.Tensor, actual_xy: Optional[torch.Tensor] = None) -> ReferencePose:
        """Reference for the next control step.

        ``root_xy`` is the planar root position the new frame is integrated from (the previous
        reference frame, or the character's actual root when anchoring closed-loop), ``yaw`` the
        heading the frame is anchored to (the character's actual heading), and ``actual_xy`` the
        character's actual planar root, used for steering and arrival decisions (defaults to ``root_xy``).
        """
        device = root_xy.device
        if actual_xy is None:
            actual_xy = root_xy
        distance = float((self.destination - actual_xy).norm()) if self.destination is not None else 0.0
        if self.previous is not None:
            self._advance(distance)
        segment = self._segment()
        f = self.frame
        forward, lateral, dyaw = float(segment.step_forward[f]), float(segment.step_lateral[f]), float(segment.step_yaw[f])
        if self.phase == "walk" and self.destination is not None:
            desired = torch.atan2(self.destination[1] - actual_xy[1], self.destination[0] - actual_xy[0]) - self.travel_angle
            error = float(wrap_angle(desired - yaw))
            limit = self.turn_rate / self.fps
            dyaw = max(-limit, min(limit, error))
            if distance < self.slow_radius:            # ease in before the stop clip takes over
                forward *= max(0.5, distance / self.slow_radius)
            if abs(error) > math.radians(60):          # turn mostly in place for large errors
                forward *= 0.35
        new_yaw = wrap_angle(yaw + dyaw)
        rot = yaw_quat(new_yaw)
        planar = quat_rotate(rot, torch.tensor([forward, lateral, 0.0], device=device))
        new_xy = root_xy + planar[:2]
        rot_b = rot.unsqueeze(0).expand(segment.rel_rot[f].shape)
        body_pos = quat_rotate(rot_b, segment.rel_pos[f]).clone()
        body_pos[:, :2] += new_xy
        body_rot = quat_mul(rot_b, segment.rel_rot[f])
        local_rot = segment.local_rot[f].clone()
        local_rot[ROOT] = body_rot[ROOT]            # the root's local rotation is its global rotation
        pose = ReferencePose(rigid_body_pos=body_pos, rigid_body_rot=body_rot, local_rot=local_rot,
                             dof_pos=segment.dof_pos[f].clone(), dof_vel=segment.dof_vel[f].clone(),
                             contacts=segment.contacts[f].clone(), phase=self.phase, root_xy=new_xy, yaw=new_yaw)
        if self.blend_left > 0 and self.blend_from is not None:
            t = 1.0 - self.blend_left / (self.blend_frames + 1)
            source = self.blend_from
            offset = (pose.rigid_body_pos[ROOT] - source.rigid_body_pos[ROOT])
            shifted = source.rigid_body_pos + offset
            pose.rigid_body_pos = (1 - t) * shifted + t * pose.rigid_body_pos
            pose.rigid_body_rot = quat_slerp(source.rigid_body_rot, pose.rigid_body_rot, t)
            pose.local_rot = quat_slerp(source.local_rot, pose.local_rot, t)
            pose.local_rot[ROOT] = pose.rigid_body_rot[ROOT]
            pose.dof_pos = (1 - t) * source.dof_pos + t * pose.dof_pos
            pose.dof_vel = (1 - t) * source.dof_vel + t * pose.dof_vel
            self.blend_left -= 1
        self.previous = pose
        return pose


def build_default_walker(lib, walk_clip: int = 30, stop_clip: int = 30, idle_clip: int = 30,
                         idle_seconds: float = 2.0) -> tuple[ReferenceWalker, dict]:
    """Default segments from the pinned seed-mini clip set, all from ``happy_walk_ff_stop_180`` (30):
    the only clip that walks straight ahead (the number in a clip name is its travel direction
    relative to facing), decelerates and stands. Using one clip keeps the travel direction in the
    heading frame identical across the walk, stop and idle segments."""
    walk_frames = clip_frames(lib, walk_clip)
    start, period, closing = find_walk_cycle(walk_frames, search_start=0)
    walk = make_segment(walk_frames, start, start + period, f"{walk_frames['name']}[{start}:{start + period}]")
    stop_frames = clip_frames(lib, stop_clip)
    stop_at = find_stop(stop_frames)
    stop_begin = max(0, stop_at - int(1.0 * stop_frames["fps"]))
    stop = make_segment(stop_frames, stop_begin, stop_at + 1, f"{stop_frames['name']}[{stop_begin}:{stop_at + 1}]")
    idle_frames = clip_frames(lib, idle_clip)
    idle_end = min(idle_frames["gts"].shape[0], stop_at + 1 + int(idle_seconds * idle_frames["fps"]))
    idle = make_segment(idle_frames, stop_at + 1, idle_end, f"{idle_frames['name']}[{stop_at + 1}:{idle_end}]")
    # Idle loops in place: remove residual drift so standing stays put.
    idle.step_forward.zero_(); idle.step_lateral.zero_(); idle.step_yaw.zero_()
    info = {"walk": {"clip": walk_clip, "name": walk.name, "frames": walk.frames, "closing_m": round(closing, 4), "speed_mps": round(walk.mean_speed, 3)},
            "stop": {"clip": stop_clip, "name": stop.name, "frames": stop.frames},
            "idle": {"clip": idle_clip, "name": idle.name, "frames": idle.frames}}
    return ReferenceWalker(walk=walk, stop=stop, idle=idle), info
