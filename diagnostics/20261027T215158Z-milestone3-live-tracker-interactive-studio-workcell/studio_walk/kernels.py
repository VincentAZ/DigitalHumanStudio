"""Pure tensor kernels for destination walking: rewards, termination and metrics.

Every function is a plain tensor function bound through ``MdpComponent`` so it can be
compiled and pickled by module path. Quaternions are xyzw (w_last=True), metres, Z-up.
"""
import torch
from torch import Tensor

from protomotions.utils.rotations import quat_rotate


def planar_target_geometry(root_pos: Tensor, tar_pos: Tensor):
    """Return (distance, unit direction) from the root to the target in the XY plane."""
    delta = tar_pos[..., :2] - root_pos[..., :2]
    dist = torch.linalg.norm(delta, dim=-1)
    direction = delta / dist.clamp_min(1e-6).unsqueeze(-1)
    return dist, direction


def body_up_z(root_rot: Tensor) -> Tensor:
    """World Z component of the pelvis local +Z axis (1 = upright, 0 = lying)."""
    up = torch.zeros(root_rot.shape[:-1] + (3,), device=root_rot.device, dtype=root_rot.dtype)
    up[..., 2] = 1.0
    return quat_rotate(root_rot, up, True)[..., 2]


def forward_xy(root_rot: Tensor, forward_x: float, forward_y: float) -> Tensor:
    """Unit world XY direction of the robot's anatomical forward axis."""
    axis = torch.zeros(root_rot.shape[:-1] + (3,), device=root_rot.device, dtype=root_rot.dtype)
    axis[..., 0] = forward_x
    axis[..., 1] = forward_y
    world = quat_rotate(root_rot, axis, True)[..., :2]
    return world / torch.linalg.norm(world, dim=-1, keepdim=True).clamp_min(1e-6)


def compute_progress_velocity_rew(
    root_pos: Tensor,
    root_vel: Tensor,
    tar_pos: Tensor,
    tar_proximity_threshold: float,
    target_speed: float = 1.2,
    slow_down_seconds: float = 1.0,
    err_scale: float = 1.0,
    still_scale: float = 4.0,
) -> Tensor:
    """Walk toward the destination at a distance-scaled speed, then be still.

    Far from the target the desired closing speed is ``target_speed``; inside
    ``slow_down_seconds`` of travel it decays linearly to zero, which rewards slowing
    before arrival. Inside the proximity radius the reward is a stillness term.
    """
    dist, direction = planar_target_geometry(root_pos, tar_pos)
    planar_vel = root_vel[..., :2]
    closing_speed = (planar_vel * direction).sum(dim=-1)
    desired = (dist / slow_down_seconds).clamp(max=target_speed)
    walking = torch.exp(-err_scale * (closing_speed - desired) ** 2)
    still = torch.exp(-still_scale * (planar_vel ** 2).sum(dim=-1))
    return torch.where(dist < tar_proximity_threshold, still, walking)


def compute_standing_rew(
    root_pos: Tensor,
    root_vel: Tensor,
    root_ang_vel: Tensor,
    tar_pos: Tensor,
    tar_proximity_threshold: float,
    lin_scale: float = 3.0,
    ang_scale: float = 0.3,
) -> Tensor:
    """Stand still (low planar and yaw velocity) once inside the proximity radius."""
    dist, _ = planar_target_geometry(root_pos, tar_pos)
    lin = (root_vel[..., :2] ** 2).sum(dim=-1)
    yaw = root_ang_vel[..., 2] ** 2
    still = torch.exp(-lin_scale * lin - ang_scale * yaw)
    return torch.where(dist < tar_proximity_threshold, still, torch.zeros_like(still))


def compute_upright_rew(
    root_pos: Tensor,
    root_rot: Tensor,
    ground_heights: Tensor,
    standing_height: float = 0.85,
    height_scale: float = 20.0,
    tilt_scale: float = 5.0,
) -> Tensor:
    """Keep the pelvis upright and at or above a standing height."""
    tilt = torch.exp(-tilt_scale * (1.0 - body_up_z(root_rot)).clamp_min(0.0))
    height = root_pos[..., 2] - ground_heights
    deficit = (standing_height - height).clamp_min(0.0)
    tall = torch.exp(-height_scale * deficit ** 2)
    return 0.5 * tilt + 0.5 * tall


def compute_facing_rew(
    root_pos: Tensor,
    root_rot: Tensor,
    tar_pos: Tensor,
    tar_proximity_threshold: float,
    forward_x: float = 0.0,
    forward_y: float = -1.0,
) -> Tensor:
    """Face the destination while away from it (cosine of the facing error, clamped at 0)."""
    dist, direction = planar_target_geometry(root_pos, tar_pos)
    facing = (forward_xy(root_rot, forward_x, forward_y) * direction).sum(dim=-1).clamp_min(0.0)
    return torch.where(dist < tar_proximity_threshold, torch.ones_like(facing), facing)


def compute_fall_term(
    root_pos: Tensor,
    root_rot: Tensor,
    ground_heights: Tensor,
    progress_buf: Tensor,
    min_root_height: float = 0.5,
    min_up_z: float = 0.3,
    grace_steps: int = 5,
) -> Tensor:
    """Fall when the pelvis drops below ``min_root_height`` or tilts past ``min_up_z``.

    The same rule is used for training termination and for scoring a fall in the
    acceptance harness, so a fall ends the attempt in both places.
    """
    height = root_pos[..., 2] - ground_heights
    fallen = (height < min_root_height) | (body_up_z(root_rot) < min_up_z)
    return fallen & (progress_buf > grace_steps)


__all__ = [
    "planar_target_geometry",
    "body_up_z",
    "forward_xy",
    "compute_progress_velocity_rew",
    "compute_standing_rew",
    "compute_upright_rew",
    "compute_facing_rew",
    "compute_fall_term",
]
