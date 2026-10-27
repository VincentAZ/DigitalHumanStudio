#!/usr/bin/env python3
"""Independent CPU audit of Milestone 3 evaluation runs (no torch, no simulator).

Re-scores every trial from the saved per-step traces with the acceptance rule, compares the
result with the harness's own trials.json, re-hashes the artifact manifest, checks finite
values and monotonic time, and writes an aggregate acceptance record. Run from any
directory with the project path; the script locates the project from its own location.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DT = 1.0 / 30.0
ARRIVAL_RADIUS, LOOSE_RADIUS, DEADLINE_S, HOLD_SPEED, HOLD_S = 0.3, 0.5, 15.0, 0.15, 2.0
FALL_HEIGHT, FALL_UP_Z = 0.5, 0.3
DEADLINE_STEPS, HOLD_STEPS = round(DEADLINE_S / DT), round(HOLD_S / DT)


def rescore(steps, reference_step):
    """steps: list of dicts with distance, speed, root_pos, up_z (0-indexed order)."""
    fallen = [(s["root_pos"][2] < FALL_HEIGHT) or (s["up_z"] < FALL_UP_Z) for s in steps]
    fall_step = fallen.index(True) if any(fallen) else None
    arrival = next((i for i in range(reference_step, len(steps)) if steps[i]["distance"] < ARRIVAL_RADIUS), None)
    reasons = []
    if arrival is None or arrival - reference_step > DEADLINE_STEPS:
        reasons.append("no_arrival_within_15s")
    if fall_step is not None:
        reasons.append("fell")
    settle = None
    if arrival is not None:
        for start in range(arrival, len(steps) - HOLD_STEPS + 1):
            window = steps[start:start + HOLD_STEPS]
            if all(w["speed"] < HOLD_SPEED and w["distance"] < ARRIVAL_RADIUS for w in window):
                settle = start
                break
        if settle is None:
            reasons.append("no_two_second_hold_within_0.3m")
    return {"success": not reasons, "failure_reasons": reasons, "arrival_step": arrival, "fall_step": fall_step,
            "settle_step_strict": settle}


def audit_run(evidence_dir: Path):
    run_contract = json.loads((evidence_dir / "run-contract.json").read_text())
    trials = json.loads((evidence_dir / "trials.json").read_text())
    measurements = json.loads((evidence_dir / "measurements.json").read_text())
    manifest = json.loads((evidence_dir / "artifact-manifest.json").read_text())
    outcome = json.loads((evidence_dir / "outcome.json").read_text())
    artifact_root = Path(manifest["root"])
    problems = []
    hashed = 0
    for relative, record in manifest["files"].items():
        path = artifact_root / relative
        if not path.exists():
            problems.append(f"missing artifact {relative}")
            continue
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                problems.append(f"hash mismatch {relative}")
        hashed += 1
    by_trial = {}
    scenario_set = run_contract["scenario_set"]
    if run_contract.get("record"):
        for trial in trials:
            lines = (artifact_root / f"trial-{trial['trial_id']:03d}" / "trace.jsonl").read_text().splitlines()
            by_trial[trial["trial_id"]] = [json.loads(l) for l in lines]
            for step in by_trial[trial["trial_id"]]:
                step["speed"] = math.hypot(step["root_vel"][0], step["root_vel"][1])
    else:
        for line in (artifact_root / f"trace-{scenario_set}.jsonl").read_text().splitlines():
            record = json.loads(line)
            by_trial.setdefault(record["trial_id"], []).append(record)
    mismatches = []
    recomputed_successes = 0
    for trial in trials:
        steps = by_trial.get(trial["trial_id"], [])
        if len(steps) != trial["horizon_steps"]:
            problems.append(f"trial {trial['trial_id']} has {len(steps)} trace steps, expected {trial['horizon_steps']}")
            continue
        if any(steps[i]["step"] != i + 1 for i in range(len(steps))):
            problems.append(f"trial {trial['trial_id']} non-monotonic step counter")
        for step in steps:
            values = [*step["root_pos"], step["distance"], step["up_z"], step["speed"], *step["target_xy"]]
            if not all(math.isfinite(v) for v in values):
                problems.append(f"trial {trial['trial_id']} non-finite value at step {step['step']}")
                break
        result = rescore(steps, trial["reference_step"])
        recomputed_successes += result["success"]
        if result["success"] != trial["success"] or sorted(result["failure_reasons"]) != sorted(trial["failure_reasons"]):
            mismatches.append({"trial_id": trial["trial_id"], "harness": trial["failure_reasons"], "audit": result["failure_reasons"]})
    if recomputed_successes != measurements["successes"]:
        problems.append(f"successes {measurements['successes']} reported vs {recomputed_successes} recomputed")
    if mismatches:
        problems.append(f"{len(mismatches)} trial scoring mismatches")
    return {
        "evidence": str(evidence_dir.relative_to(ROOT)), "controller": run_contract["controller"], "set": scenario_set,
        "record": bool(run_contract.get("record")), "trials": len(trials), "successes": measurements["successes"],
        "recomputed_successes": recomputed_successes, "falls": measurements["falls"],
        "arrived_within_15s": measurements["arrived_within_15s"], "run_status": outcome["status"],
        "adapter_sha256": run_contract.get("adapter_sha256"), "prior_sha256": run_contract.get("prior_sha256"),
        "files_hash_verified": hashed, "problems": problems, "mismatches": mismatches[:10],
        "gate_passed_90_percent": recomputed_successes >= 0.9 * len(trials) if trials else False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dirs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [audit_run(d.resolve()) for d in args.evidence_dirs]
    status = "passed" if all(not r["problems"] and r["run_status"] == "passed" for r in results) else "failed"
    document = {"status": status, "acceptance_rule": {"arrival_radius_m": ARRIVAL_RADIUS, "deadline_s": DEADLINE_S,
                "hold_speed_mps": HOLD_SPEED, "hold_s": HOLD_S, "fall_height_m": FALL_HEIGHT, "fall_up_z": FALL_UP_Z},
                "runs": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    for r in results:
        print(f"{r['controller']:8s} {r['set']:9s} {'record' if r['record'] else 'batch ':6s} "
              f"{r['recomputed_successes']:3d}/{r['trials']:3d} falls={r['falls']:3d} problems={len(r['problems'])}")
    print("audit", status)
    sys.exit(0 if status == "passed" else 1)


if __name__ == "__main__":
    main()
