#!/usr/bin/env python3
"""Assemble the Milestone 3 acceptance record from existing evidence (CPU only).

Inputs are evidence directories already produced by the launchers: training runs
(outcome.json, train-contract.json, metrics.jsonl), evaluation audits
(trace-audit.json from scripts/audit_milestone3.py) and live sessions (outcome.json).
The script never changes a measurement; it only gathers them, applies the plan's
gates and writes config/milestone3.json plus a diagnostics copy. A failed gate is
written as failed.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES = {"walking_successes_per_100": 90, "redirect_successes_per_100": 90}


def load(path):
    return json.loads(Path(path).read_text())


def rel(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def training_record(evidence_dir: Path):
    outcome = load(evidence_dir / "outcome.json")
    contract = load(evidence_dir / "train-contract.json")
    metrics = [json.loads(l) for l in (evidence_dir / "metrics.jsonl").read_text().splitlines() if l.strip()]
    last = metrics[-1] if metrics else {}
    hashes = {}
    sha_file = evidence_dir / "checkpoints.sha256"
    if sha_file.exists():
        for line in sha_file.read_text().splitlines():
            digest, _, name = line.partition("  ")
            hashes[name] = digest
    return {
        "evidence": rel(evidence_dir), "stage": contract["stage"], "seed": int(contract["seed"]),
        "experiment_name": contract["experiment_name"], "num_envs": int(contract["num_envs"]),
        "batch_size": int(contract["batch_size"]), "wall_clock_cap_seconds": int(contract["wall_clock_seconds"]),
        "warm_start_checkpoint": contract.get("warm_start_checkpoint") or None, "status": outcome["status"],
        "process_exit_code": outcome["process_exit_code"], "epochs": len(metrics),
        "environment_steps": last.get("step_count"), "elapsed_seconds": last.get("elapsed_seconds"),
        "max_gpu_memory_gib": max((m.get("max_gpu_memory_gib") or 0) for m in metrics) if metrics else None,
        "final_episode_length": last.get("info/episode_length"), "final_fall_rate": last.get("env/termination/fall_mean"),
        "final_unnormalized_reward": last.get("rewards/unnormalized_task_rewards"),
        "final_sft_accuracy": last.get("sft/accuracy"), "checkpoint_sha256": hashes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", nargs="*", type=Path, default=[], help="training evidence directories")
    parser.add_argument("--audits", nargs="*", type=Path, default=[], help="trace-audit.json files")
    parser.add_argument("--live", nargs="*", type=Path, default=[], help="live session evidence directories")
    parser.add_argument("--report", default="docs/MILESTONE3_REPORT.md")
    parser.add_argument("--output", type=Path, default=ROOT / "config/milestone3.json")
    parser.add_argument("--copy-to", type=Path, default=None, help="diagnostics directory for a copy")
    parser.add_argument("--note", action="append", default=[], help="limitation or note to record")
    args = parser.parse_args()

    training = [training_record(d.resolve()) for d in args.training]
    runs = []
    for audit_path in args.audits:
        audit = load(audit_path)
        for run in audit["runs"]:
            run = dict(run)
            run["audit"] = rel(audit_path)
            run["audit_status"] = audit["status"]
            runs.append(run)
    live = []
    for d in args.live:
        outcome = load(Path(d) / "outcome.json")
        live.append({"evidence": rel(d), **{k: outcome[k] for k in (
            "status", "commands", "command_results", "final_state", "resets", "steps", "frames")}})

    def best_per_seed(controller, scenario_set):
        table = {}
        for run in runs:
            if run["controller"] != controller or run["set"] != scenario_set or run["record"]:
                continue
            seed = next((int(t["seed"]) for t in training if t["stage"] == "rlft" and t["experiment_name"] and
                         run.get("adapter_sha256") and run["adapter_sha256"] in t["checkpoint_sha256"].values()), None)
            key = seed if seed is not None else run["evidence"]
            table[key] = {"successes": run["recomputed_successes"], "trials": run["trials"], "falls": run["falls"],
                          "evidence": run["evidence"], "problems": run["problems"]}
        return table

    summary = {
        "adapter": {s: best_per_seed("adapter", s) for s in ("flat", "redirect", "push")},
        "prior_baseline": {s: best_per_seed("prior", s) for s in ("flat", "redirect", "push")},
    }
    seeds_flat = summary["adapter"]["flat"]
    seeds_redirect = summary["adapter"]["redirect"]
    passing_seeds = [k for k, v in seeds_flat.items() if v["trials"] and v["successes"] >= GATES["walking_successes_per_100"] * v["trials"] / 100
                     and k in seeds_redirect and seeds_redirect[k]["successes"] >= GATES["redirect_successes_per_100"] * seeds_redirect[k]["trials"] / 100
                     and not v["problems"]]
    audits_ok = all(r["audit_status"] == "passed" and not r["problems"] for r in runs) if runs else False
    training_ok = all(t["status"] == "passed" for t in training) if training else False
    live_ok = all(l["status"] == "passed" for l in live) if live else False
    status = "passed" if passing_seeds and audits_ok and training_ok and live_ok else "failed"
    record = {
        "schema_version": 1, "status": status, "milestone": 3,
        "scope": "Destination-directed walking adapter on the frozen SOMA GPC prior; separate standalone workers; Milestone 2 deferred",
        "gates": GATES, "passing_seeds": passing_seeds,
        "seed_distribution": {"flat": {str(k): f"{v['successes']}/{v['trials']}" for k, v in seeds_flat.items()},
                              "redirect": {str(k): f"{v['successes']}/{v['trials']}" for k, v in seeds_redirect.items()},
                              "push": {str(k): f"{v['successes']}/{v['trials']}" for k, v in summary["adapter"]["push"].items()}},
        "prior_baseline": {s: {str(k): f"{v['successes']}/{v['trials']}" for k, v in t.items()} for s, t in summary["prior_baseline"].items()},
        "training": training, "evaluation_runs": runs, "live_sessions": live,
        "physics_hz": 120, "control_hz": 30, "report": args.report, "limitations": args.note,
    }
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    if args.copy_to is not None:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        (args.copy_to / "acceptance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({k: record[k] for k in ("status", "passing_seeds", "seed_distribution", "prior_baseline")}, indent=2))


if __name__ == "__main__":
    main()
