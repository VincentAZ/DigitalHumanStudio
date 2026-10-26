#!/usr/bin/env python3
"""Generate the reserved Milestone 3 acceptance scenarios (deterministic, CPU only).

Scenario sets:
  flat      100 trials: start pose from a reserved clip, destination 1-5 m away.
  redirect  100 trials: as flat, plus one destination change while walking.
  push      100 trials: as flat, plus one reproducible horizontal velocity impulse.
Destinations are expressed relative to the character's initial pelvis heading so that
every controller is scored on identical geometry regardless of where it spawns.
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from studio_walk import RESERVED_EVALUATION_MOTION_IDS  # noqa: E402

SEED = 20261026
COUNT = 100


def base_trial(rng, index):
    return {
        "id": index,
        "start_motion_id": rng.choice(RESERVED_EVALUATION_MOTION_IDS),
        "start_phase": round(rng.uniform(0.0, 0.8), 4),
        "distance_m": round(rng.uniform(1.0, 5.0), 3),
        "bearing_deg": round(rng.uniform(-180.0, 180.0), 2),
        "friction": round(rng.uniform(0.5, 1.25), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "config/milestone3-scenarios.json")
    args = parser.parse_args()
    rng = random.Random(SEED)
    flat = [base_trial(rng, i) for i in range(COUNT)]
    redirect = []
    for i in range(COUNT):
        trial = base_trial(rng, i)
        trial.update({
            "change_time_s": round(rng.uniform(1.5, 4.0), 3),
            "second_distance_m": round(rng.uniform(1.0, 5.0), 3),
            "second_bearing_deg": round(rng.uniform(-180.0, 180.0), 2),
        })
        redirect.append(trial)
    push = []
    for i in range(COUNT):
        trial = base_trial(rng, i)
        trial.update({
            "push_time_s": round(rng.uniform(1.0, 3.0), 3),
            "push_heading_deg": round(rng.uniform(-180.0, 180.0), 2),
            "push_speed_mps": 0.1,
        })
        push.append(trial)
    document = {
        "schema_version": 1,
        "generator": "scripts/milestone3_scenarios.py",
        "seed": SEED,
        "reserved_start_motion_ids": list(RESERVED_EVALUATION_MOTION_IDS),
        "friction": "robot contact static/dynamic friction coefficient applied to every collision shape; floor keeps the simulator default of 1.0",
        "geometry": "distances in metres; bearings in degrees relative to the initial pelvis heading (flat/redirect first target, push) or to the first target in world heading frame (second target)",
        "acceptance": {
            "arrival_radius_m": 0.3,
            "arrival_deadline_s": 15.0,
            "hold_speed_mps": 0.15,
            "hold_seconds": 2.0,
            "fall": "pelvis height below 0.5 m or pelvis up-axis z below 0.3 at any step",
            "required_successes_per_100": 90,
        },
        "sets": {"flat": flat, "redirect": redirect, "push": push},
    }
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(f"Wrote {args.output} with {sum(len(v) for v in document['sets'].values())} trials")


if __name__ == "__main__":
    main()
