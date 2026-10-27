#!/usr/bin/env python3
"""Print a compact trend table from a Milestone 3 training metrics.jsonl (CPU only).

Reads the per-epoch records written by scripts/milestone3_train.py and shows reward
components, fall/termination rate, episode length, throughput and GPU memory at evenly
spaced epochs plus the latest one, so a failing run is visible without TensorBoard.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = [
    ("epoch", "epoch"), ("min", "elapsed_seconds"), ("steps", "step_count"),
    ("ep_len", "info/episode_length"), ("ep_rew", "info/episode_reward"),
    ("raw_rew", "rewards/unnormalized_task_rewards"),
    ("target", "env/raw_r/target_mean"), ("progress", "env/raw_r/progress_mean"),
    ("standing", "env/raw_r/standing_mean"), ("upright", "env/raw_r/upright_mean"),
    ("facing", "env/raw_r/facing_mean"), ("fall%", "env/termination/fall_mean"),
    ("sft_loss", "sft/loss"), ("sft_acc", "sft/accuracy"),
    ("fps", "times/fps_last_epoch"), ("gpu_gib", "max_gpu_memory_gib"),
]


def fmt(key, value):
    if value is None:
        return "-"
    if key == "min":
        return f"{value / 60:.0f}"
    if key == "steps":
        return f"{value / 1e6:.1f}M"
    if key == "fall%":
        return f"{100 * value:.1f}"
    if key in ("epoch",):
        return f"{int(value)}"
    return f"{value:.3f}" if abs(value) < 100 else f"{value:.0f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", nargs="?", type=Path, default=None,
                        help="metrics.jsonl (default: newest artifacts/milestone3/train-*/metrics.jsonl)")
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="print the latest record as JSON")
    args = parser.parse_args()
    path = args.metrics
    if path is None:
        candidates = sorted((ROOT / "artifacts/milestone3").glob("train-*/metrics.jsonl"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            sys.exit("no metrics files found")
        path = candidates[-1]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        sys.exit(f"{path}: no epochs yet")
    print(f"{path}  epochs={len(rows)}")
    if args.json:
        print(json.dumps(rows[-1], indent=2))
        return
    present = [(label, key) for label, key in COLUMNS if any(key in r for r in rows)]
    stride = max(1, len(rows) // max(1, args.rows - 1))
    selected = rows[::stride]
    if selected[-1] is not rows[-1]:
        selected.append(rows[-1])
    print(" ".join(f"{label:>9s}" for label, _ in present))
    for r in selected:
        print(" ".join(f"{fmt(label, r.get(key)):>9s}" for label, key in present))


if __name__ == "__main__":
    main()
