#!/usr/bin/env bash
# Train one walking-adapter seed: supervised bootstrap (shared, run once) then PPO fine-tuning.
# usage: run_milestone3_seed.sh <seed> <sft_wall_seconds> <rlft_wall_seconds> [sft_results_dir]
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
seed=${1:?seed}; sft_wall=${2:?sft_wall_seconds}; rlft_wall=${3:?rlft_wall_seconds}; sft_dir=${4:-}
if [[ -z "$sft_dir" ]]; then
    "$project_root/scripts/run_milestone3_train.sh" sft 0 1024 1024 "$sft_wall" m3_sft_walk
    sft_dir=$(ls -d "$project_root"/artifacts/milestone3/train-sft-m3_sft_walk-*/results/m3_sft_walk | tail -1)
fi
[[ -f "$sft_dir/last.ckpt" ]] || { echo "SFT checkpoint missing in $sft_dir" >&2; exit 4; }
"$project_root/scripts/run_milestone3_train.sh" rlft "$seed" 2048 2048 "$rlft_wall" "m3_rlft_walk_seed$seed" --warm-start "$sft_dir/last.ckpt"
