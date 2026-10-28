#!/opt/IsaacLab/.venv/bin/python
"""Build the shipped skill catalog from the pinned, licensed clip set.

Every motion of the BONES-SEED seed-mini file (pinned in config/milestone1-assets.lock.json, licence
recorded in config/milestone1-license.json) becomes a skill folder ``skills/<id>/`` with
``skill.json`` (name, description, category, tags, measured duration/pose/travel, source, licence,
provenance) and a stick-figure ``thumbnail.png`` (committed) plus ``preview.gif`` (generated, not
committed). Deterministic: re-running rewrites identical metadata. Runs on the CPU inside the pinned
image through scripts/build_skill_catalog.sh; existing folders of other kinds (sequences, generated
skills) are left alone.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_walk.skill_lib import analyse_frames, frames_from_motion_dict, write_previews  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--assets", type=Path, required=True, help="asset root (the Milestone 1 asset tree)")
parser.add_argument("--config", type=Path, required=True, help="project config directory (lock + licence records)")
parser.add_argument("--skills", type=Path, required=True, help="skills directory to write")
parser.add_argument("--no-gif", action="store_true")
args = parser.parse_args()

MOTION_FILE = "data/motion_for_trackers/soma23_bones_seed_mini.pt"
lock = json.loads((args.config / "milestone1-assets.lock.json").read_text())
entry = next(e for e in lock["files"] if e["path"] == MOTION_FILE)
licence_record = json.loads((args.config / "milestone1-license.json").read_text())
LICENCE = {"name": "BONES-SEED licence", "url": licence_record.get("license_url"), "record": "config/milestone1-license.json",
           "eligibility": licence_record.get("eligibility_status"), "attribution": licence_record.get("motion_data_attribution")}

CATEGORY_RULES = [
    ("dance", r"dance|dancing|vouge|vogue|hiphop|worm|mohak|routine"),
    ("floor", r"fall_down|stumble|kneeling|on_ground|all_fours|crawl|zombie_crawl"),
    ("locomotion", r"walk|jog|run|turn|jump|quickstep|crutches|step"),
    ("idle", r"idle"),
    ("gesture", r"point|kisses|speak|threaten|finger_gun|dont_touch|reaction|afraid|confusion|cry|wave|searching"),
    ("action", r"door|putting|put_down|one_hand|two_hands|stretch|warm_up|colia|gun|rifle|sword|spear|combat"),
]
STYLE_WORDS = {"happy", "sad", "angry", "scared", "drunk", "injured", "tired", "old", "child", "obese", "macho", "leaning", "high_energy",
               "zombie", "victory", "warm", "medium", "small", "big", "heavy", "light", "normal_pace", "fast", "max"}
DROP_TOKENS = {"ff", "R", "L", "V002", "V001"}


def parse_name(motion_file: str) -> dict:
    base = motion_file.replace(".motion", "")
    stem, _, actor = base.partition("__")
    tokens = stem.split("_")
    take = None
    if tokens and re.fullmatch(r"\d{3}", tokens[-1]) and int(tokens[-1]) < 100:
        take = int(tokens.pop())
    mirrored = "R" in tokens
    direction = next((int(t) for t in tokens if re.fullmatch(r"\d{3}", t)), None)
    words = [t for t in tokens if t not in DROP_TOKENS and not re.fullmatch(r"\d{3}", t)]
    phase = next((w for w in ("loop", "start", "stop") if w in words), None)
    text = "_".join(words)
    category = next((c for c, pattern in CATEGORY_RULES if re.search(pattern, text)), "action")
    styles = [w for w in words if w in STYLE_WORDS]
    name = " ".join(w.replace("vouge", "vogue") for w in words).strip()
    name = name[:1].upper() + name[1:]
    return {"name": name, "words": words, "take": take, "mirrored": mirrored, "direction": direction, "phase": phase,
            "category": category, "styles": styles, "actor": actor}


def skill_id(parsed: dict, motion_id: int) -> str:
    base = "_".join(parsed["words"])[:48].strip("_")
    suffix = f"_r{parsed['take']:02d}" if parsed["take"] is not None else ""
    return re.sub(r"[^a-z0-9_]", "", (base + suffix + f"_m{motion_id:02d}").lower())


def describe(parsed: dict, analysis: dict) -> str:
    parts = [f"{parsed['name']}."]
    parts.append(f"{analysis['duration_s']:.1f} s, starts {analysis['entry_pose']}, ends {analysis['exit_pose']}")
    if analysis["travel_m"] >= 0.3:
        parts[-1] += f", travels {analysis['travel_m']:.1f} m"
    if abs(analysis["turn_deg"]) >= 45:
        parts[-1] += f", turns {analysis['turn_deg']:+.0f}°"
    parts[-1] += "."
    if parsed["phase"] == "loop":
        parts.append("Loops.")
    if parsed["mirrored"]:
        parts.append("Right-side variant.")
    parts.append(f"BONES-SEED motion capture, actor {parsed['actor']}.")
    return " ".join(parts)


def main():
    data = torch.load(args.assets / MOTION_FILE, map_location="cpu", weights_only=False)
    count = int(data["motion_num_frames"].shape[0])
    written = []
    for motion_id in range(count):
        frames = frames_from_motion_dict(data, motion_id)
        parsed = parse_name(frames["name"])
        analysis = analyse_frames(frames)
        sid = skill_id(parsed, motion_id)
        folder = args.skills / sid
        folder.mkdir(parents=True, exist_ok=True)
        tags = sorted(set([parsed["category"], analysis["entry_pose"]] + parsed["styles"] + ([parsed["phase"]] if parsed["phase"] else [])
                          + (["travels"] if analysis["travel_m"] >= 0.3 else ["in place"]) + ["SOMA-23", "mocap"]))
        meta = {"id": sid, "kind": "clip", "name": parsed["name"], "description": describe(parsed, analysis), "category": parsed["category"],
                "tags": tags, "loop": parsed["phase"] == "loop", **analysis,
                "source": {"kind": "motion_lib", "asset_root": lock["asset_root"], "file": MOTION_FILE, "sha256": entry["sha256"],
                           "motion_id": motion_id, "clip": frames["name"], "frames": [0, analysis["frames"]]},
                "licence": LICENCE,
                "provenance": {"dataset": "BONES-SEED seed-mini subset shipped with ProtoMotions", "protomotions_revision": lock["revision"],
                               "source_url": entry["source_url"], "actor": parsed["actor"], "take": parsed["take"],
                               "direction_token": parsed["direction"], "right_side_variant": parsed["mirrored"],
                               "generated_by": "scripts/build_skill_catalog.py"}}
        (folder / "skill.json").write_text(json.dumps(meta, indent=1) + "\n")
        write_previews(frames, folder, gif=not args.no_gif)
        written.append(sid)
        print(f"{motion_id:2d} {sid:60s} {parsed['category']:10s} {analysis['duration_s']:5.1f}s {analysis['entry_pose']}->{analysis['exit_pose']}")
    index = {"source_file": MOTION_FILE, "sha256": entry["sha256"], "count": len(written), "skills": written}
    (args.skills / "shipped-catalog.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"wrote {len(written)} skills to {args.skills}")


if __name__ == "__main__":
    main()
