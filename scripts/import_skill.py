#!/opt/IsaacLab/.venv/bin/python
"""Import a motion clip into the skill library as ``skills/<id>/``.

Inputs: a Kimodo / SOMA npz (``local_rot_mats`` [T,77,3,3] + ``posed_joints`` [T,77,3], 30 fps, Y-up,
converted with ProtoMotions' own SOMA-23 pipeline), a ProtoMotions ``.motion`` file, or a packaged
MotionLib ``.pt`` with a motion id. Writes ``motion.pt`` (the clip as a ``.motion`` dictionary),
``skill.json`` with the measured motion, licence and provenance, plus the stick-figure previews.
Runs on the CPU inside the pinned image (scripts/generate_skill.sh and scripts/import_skill.sh call it).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_walk.skill_lib import PARENTS, analyse_frames, frames_from_motion_dict, sha256_of, write_previews  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, required=True, help=".npz (SOMA 77 joints), .motion, or packaged .pt")
parser.add_argument("--motion-id", type=int, default=0, help="motion index inside a packaged .pt")
parser.add_argument("--skills", type=Path, required=True, help="skills directory")
parser.add_argument("--id", required=True)
parser.add_argument("--name", default="")
parser.add_argument("--description", default="")
parser.add_argument("--category", default="generated")
parser.add_argument("--tags", default="", help="comma separated")
parser.add_argument("--licence", default="{}", help="JSON licence record")
parser.add_argument("--provenance", default="{}", help="JSON provenance record (prompt, model, seed, ...)")
parser.add_argument("--protomotions", type=Path, default=Path("/studio/ProtoMotions"), help="ProtoMotions checkout (its data/scripts convert SOMA npz files)")
parser.add_argument("--fps", type=float, default=30.0)
parser.add_argument("--trim-still", action="store_true", help="drop still frames at the start and end of the clip")
parser.add_argument("--no-gif", action="store_true")
args = parser.parse_args()


def quat_conj(q):
    return torch.cat([-q[..., :3], q[..., 3:]], -1)


def quat_mul(a, b):
    ax, ay, az, aw = a.unbind(-1)
    bx, by, bz, bw = b.unbind(-1)
    return torch.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                        aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def convert_npz(path: Path) -> dict:
    """Kimodo SOMA npz -> ProtoMotions RobotState dict through the pinned converter functions."""
    scripts = args.protomotions / "data" / "scripts"
    sys.path.insert(0, str(scripts))
    from protomotions.components.pose_lib import extract_kinematic_info
    from convert_soma23_to_proto import SOMASKEL77_TO_MJCF_INDICES, create_motion_from_soma23_data
    data = np.load(path, allow_pickle=True)
    local = data["local_rot_mats"]
    joints = data["posed_joints"]
    if local.shape[1] != 77:
        raise SystemExit(f"expected 77 SOMA joints, got {local.shape[1]}")
    kinematic_info = extract_kinematic_info(str(args.protomotions / "protomotions" / "data" / "assets" / "mjcf" / "soma23_humanoid.xml"))
    local23 = torch.from_numpy(local[:, SOMASKEL77_TO_MJCF_INDICES]).float()
    root = torch.from_numpy(joints[:, 0, :]).float()
    with torch.no_grad():
        motion = create_motion_from_soma23_data(local_rot_mats=local23, root_pos=root, kinematic_info=kinematic_info, fps=int(args.fps),
                                                device=torch.device("cpu"), dtype=torch.float32)
    return motion.to_dict()


suffix = args.input.suffix.lower()
if suffix == ".npz":
    motion_dict = convert_npz(args.input)
elif suffix in (".motion", ".pt"):
    motion_dict = torch.load(args.input, map_location="cpu", weights_only=False)
else:
    raise SystemExit(f"unsupported input {args.input}")
if "gts" in motion_dict:                                   # packaged library: cut the chosen motion out
    frames = frames_from_motion_dict(motion_dict, args.motion_id)
    motion_dict = {"rigid_body_pos": frames["gts"], "rigid_body_rot": frames["grs"], "local_rigid_body_rot": frames["lrs"], "dof_pos": frames["dps"],
                   "dof_vel": frames["dvs"], "rigid_body_contacts": frames["contacts"], "fps": frames["fps"]}
if "local_rigid_body_rot" not in motion_dict or motion_dict["local_rigid_body_rot"] is None:
    grs = motion_dict["rigid_body_rot"]
    local = grs.clone()
    for child, parent in enumerate(PARENTS):
        if parent >= 0:
            local[:, child] = quat_mul(quat_conj(grs[:, parent]), grs[:, child])
    motion_dict["local_rigid_body_rot"] = local
motion_dict["fps"] = float(motion_dict.get("fps", args.fps))
frames = frames_from_motion_dict(motion_dict)
if args.trim_still and frames["gts"].shape[0] > 30:
    # a frame is "still" when no body moves faster than 0.25 m/s (a wave moves the hand, not the root)
    speed = (frames["gts"][1:] - frames["gts"][:-1]).norm(dim=-1).max(dim=-1).values * frames["fps"]
    moving = (speed > 0.25).nonzero()
    if moving.numel():
        start, end = max(0, int(moving[0]) - 5), min(frames["gts"].shape[0], int(moving[-1]) + 6)
        motion_dict = {k: (v[start:end] if hasattr(v, "shape") and v.shape[:1] == frames["gts"].shape[:1] else v) for k, v in motion_dict.items()}
        frames = frames_from_motion_dict(motion_dict)
folder = args.skills / args.id
folder.mkdir(parents=True, exist_ok=True)
torch.save(motion_dict, folder / "motion.pt")
analysis = analyse_frames(frames)
analysis["fps"] = round(analysis["fps"], 3)
provenance = json.loads(args.provenance)
licence = json.loads(args.licence)
tags = sorted(set([t.strip() for t in args.tags.split(",") if t.strip()] + [args.category, analysis["entry_pose"], "SOMA-23"]
                  + (["travels"] if analysis["travel_m"] >= 0.3 else ["in place"])))
name = args.name or args.id.replace("_", " ").capitalize()
description = args.description or f"{name}. {analysis['duration_s']:.1f} s, starts {analysis['entry_pose']}, ends {analysis['exit_pose']}."
meta = {"id": args.id, "kind": "clip", "name": name, "description": description, "category": args.category, "tags": tags, "loop": False, **analysis,
        "source": {"kind": "motion_file", "file": "motion.pt", "sha256": sha256_of(folder / "motion.pt"), "frames": [0, analysis["frames"]],
                   "imported_from": args.input.name, "input_sha256": sha256_of(args.input)},
        "licence": licence, "provenance": {**provenance, "imported_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "generated_by": "scripts/import_skill.py"}}
(folder / "skill.json").write_text(json.dumps(meta, indent=1) + "\n")
write_previews(frames, folder, gif=not args.no_gif)
print(json.dumps({"skill": args.id, "name": name, "category": args.category, "duration_s": analysis["duration_s"], "frames": analysis["frames"],
                  "entry_pose": analysis["entry_pose"], "exit_pose": analysis["exit_pose"], "travel_m": analysis["travel_m"], "folder": str(folder)}))
