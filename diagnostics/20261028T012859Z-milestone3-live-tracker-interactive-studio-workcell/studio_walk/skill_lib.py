"""Skill folders: metadata, clip frames and stick-figure previews.

A skill is a folder ``skills/<id>/`` holding ``skill.json`` (metadata, licence, provenance and the
clip's source), an optional ``motion.pt`` (a ProtoMotions ``.motion`` or packaged MotionLib
dictionary) and generated previews. Shipped clips reference the pinned licensed motion file by
path and motion id instead of copying it. Everything here runs on the CPU.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Optional

BODY_NAMES = ["Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head",
              "RightShoulder", "RightArm", "RightForeArm", "RightHand",
              "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
              "RightLeg", "RightShin", "RightFoot", "RightToeBase",
              "LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase"]
PARENTS = [-1, 0, 1, 2, 3, 4, 5, 3, 7, 8, 9, 3, 11, 12, 13, 0, 15, 16, 17, 0, 19, 20, 21]
SKILL_KINDS = ("clip", "sequence")


def sha256_of(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_skill(folder: Path) -> Optional[dict]:
    try:
        meta = json.loads((folder / "skill.json").read_text())
    except (OSError, ValueError):
        return None
    meta.setdefault("id", folder.name)
    meta.setdefault("kind", "clip")
    return meta


def list_skills(skills_dir: Path) -> list[dict]:
    skills = []
    for path in sorted(skills_dir.glob("*/skill.json")):
        meta = read_skill(path.parent)
        if meta:
            skills.append(meta)
    return skills


# ---------------------------------------------------------------- frames
def frames_from_motion_dict(data: dict, motion_id: int = 0, fps_default: float = 30.0) -> dict:
    """Frames of one motion from a loaded MotionLib dictionary (gts/grs/...) or a ``.motion`` dict."""
    import torch
    if "gts" in data:                                  # packaged MotionLib
        start = int(data["length_starts"][motion_id])
        count = int(data["motion_num_frames"][motion_id])
        sl = slice(start, start + count)
        fps = 1.0 / float(data["motion_dt"][motion_id])
        name = str(data["motion_files"][motion_id]) if "motion_files" in data else f"motion-{motion_id}"
        return {"gts": data["gts"][sl], "grs": data["grs"][sl], "lrs": data["lrs"][sl], "dps": data["dps"][sl],
                "dvs": data["dvs"][sl], "contacts": data["contacts"][sl], "fps": fps, "name": name}
    # a single ProtoMotions .motion file (RobotState.to_dict())
    fps = float(data.get("fps", fps_default))
    contacts = data.get("rigid_body_contacts")
    if contacts is None:
        contacts = torch.zeros(data["rigid_body_pos"].shape[:2], dtype=torch.bool)
    return {"gts": data["rigid_body_pos"], "grs": data["rigid_body_rot"], "lrs": data["local_rigid_body_rot"],
            "dps": data["dof_pos"], "dvs": data["dof_vel"], "contacts": contacts.bool(), "fps": fps,
            "name": str(data.get("name", "motion"))}


def load_skill_frames(meta: dict, folder: Path, asset_root: Path, base_lib=None, base_sha256: str = "") -> dict:
    """Frames [start, end) of a clip skill. ``base_lib`` is an already loaded MotionLib whose file
    hash is ``base_sha256``; it is reused when the skill points at the same file."""
    import torch
    source = meta["source"]
    start, end = source.get("frames", [0, None])
    if source["kind"] == "motion_lib":
        if base_lib is not None and source.get("sha256") == base_sha256:
            from studio_walk.reference_walker import clip_frames
            frames = clip_frames(base_lib, int(source["motion_id"]))
        else:
            data = torch.load(asset_root / source["file"], map_location="cpu", weights_only=False)
            frames = frames_from_motion_dict(data, int(source["motion_id"]))
    elif source["kind"] == "motion_file":
        data = torch.load(folder / source["file"], map_location="cpu", weights_only=False)
        frames = frames_from_motion_dict(data)
    else:
        raise ValueError(f"unknown skill source kind {source['kind']}")
    end = frames["gts"].shape[0] if end is None else int(end)
    if start or end != frames["gts"].shape[0]:
        frames = {k: (v[start:end] if hasattr(v, "shape") else v) for k, v in frames.items()}
    return frames


# ---------------------------------------------------------------- analysis
def pose_class(root_height: float) -> str:
    if root_height > 0.72:
        return "standing"
    if root_height > 0.42:
        return "crouching"
    return "floor"


def facing_yaw(root_rot_xyzw) -> float:
    """Yaw of the pelvis' semantic forward axis (-y in the body frame)."""
    x, y, z, w = [float(v) for v in root_rot_xyzw]
    # rotate (0,-1,0) by the quaternion
    fx = -(2 * (x * y - w * z))
    fy = -(1 - 2 * (x * x + z * z))
    return math.atan2(fy, fx)


def analyse_frames(frames: dict) -> dict:
    """Duration, pose classes, travel and turning of a clip (plain floats, for skill.json)."""
    gts = frames["gts"]
    count = int(gts.shape[0])
    fps = float(frames["fps"])
    root = gts[:, 0]
    start_h, end_h = float(root[0, 2]), float(root[-1, 2])
    min_h = float(root[:, 2].min())
    delta = root[-1, :2] - root[0, :2]
    travel = float(delta.norm())
    yaw0 = facing_yaw(frames["grs"][0, 0])
    yaw1 = facing_yaw(frames["grs"][-1, 0])
    turn = math.degrees((yaw1 - yaw0 + math.pi) % (2 * math.pi) - math.pi)
    travel_dir = math.degrees((math.atan2(float(delta[1]), float(delta[0])) - yaw0 + math.pi) % (2 * math.pi) - math.pi) if travel > 0.25 else 0.0
    speed = float((root[1:, :2] - root[:-1, :2]).norm(dim=-1).mean() * fps) if count > 1 else 0.0
    return {"frames": count, "fps": fps, "duration_s": round(count / fps, 3), "entry_pose": pose_class(start_h), "exit_pose": pose_class(end_h),
            "lowest_root_m": round(min_h, 3), "travel_m": round(travel, 3), "travel_direction_deg": round(travel_dir, 1),
            "turn_deg": round(turn, 1), "mean_speed_mps": round(speed, 3)}


# ---------------------------------------------------------------- stick figures
def _project(points, yaw: float, centre_xy, view_deg: float = 35.0):
    """Orthographic 3/4 view: the character's facing is turned to ``view_deg`` from the screen's x axis."""
    import numpy as np
    pts = np.asarray(points, dtype=np.float64).copy()
    pts[:, 0] -= centre_xy[0]
    pts[:, 1] -= centre_xy[1]
    a = math.radians(view_deg) - yaw
    c, s = math.cos(a), math.sin(a)
    x = pts[:, 0] * c - pts[:, 1] * s
    y = pts[:, 0] * s + pts[:, 1] * c
    return np.stack([x - 0.25 * y, pts[:, 2] + 0.12 * y], axis=-1)   # slight oblique for depth


def draw_figure(draw, points2d, scale: float, origin, colour, width: int = 3, head_radius: float = 0.09):
    for child, parent in enumerate(PARENTS):
        if parent < 0:
            continue
        a, b = points2d[parent], points2d[child]
        draw.line([(origin[0] + a[0] * scale, origin[1] - a[1] * scale), (origin[0] + b[0] * scale, origin[1] - b[1] * scale)],
                  fill=colour, width=width)
    hx, hy = points2d[6]
    r = head_radius * scale
    draw.ellipse([origin[0] + hx * scale - r, origin[1] - hy * scale - r, origin[0] + hx * scale + r, origin[1] - hy * scale + r], fill=colour)


def render_frame_image(gts, grs, frame: int, size=(560, 350), ghosts=(), background=(24, 30, 33)):
    """One PIL image of the skeleton at ``frame`` with faint ghost frames behind it."""
    from PIL import Image, ImageDraw
    import numpy as np
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    w, h = size
    scale = h / 2.35
    origin = (w / 2, h - 0.12 * h)
    root = np.asarray(gts[frame, 0])
    yaw = facing_yaw(grs[frame, 0])
    # floor ellipse
    draw.ellipse([origin[0] - 0.55 * scale, origin[1] - 0.09 * scale, origin[0] + 0.55 * scale, origin[1] + 0.09 * scale],
                 outline=(60, 72, 70), width=2)
    for ghost in ghosts:
        pts = _project(gts[ghost], yaw, root[:2])
        draw_figure(draw, pts, scale, origin, (62, 78, 80), width=2)
    pts = _project(gts[frame], yaw, root[:2])
    draw_figure(draw, pts, scale, origin, (189, 216, 193), width=4)
    return image


def write_previews(frames: dict, folder: Path, gif: bool = True, gif_fps: int = 10, thumbnail_size=(560, 350)):
    """thumbnail.png (mid frame with start/end ghosts) and optionally preview.gif."""
    gts, grs = frames["gts"].cpu().numpy(), frames["grs"].cpu().numpy()
    count = gts.shape[0]
    mid = count // 2
    image = render_frame_image(gts, grs, mid, size=thumbnail_size, ghosts=(0, count - 1))
    image.save(folder / "thumbnail.png", optimize=True)
    if gif and count > 1:
        step = max(1, int(round(frames["fps"] / gif_fps)))
        images = [render_frame_image(gts, grs, f, size=(280, 175)) for f in range(0, count, step)]
        images[0].save(folder / "preview.gif", save_all=True, append_images=images[1:], duration=int(1000 / gif_fps), loop=0, optimize=True)
