#!/usr/bin/env bash
# Run the same scripted route through a scene with the tracker-driven walker and a learned adapter,
# one after the other, then compose the comparison (metrics, side-by-side video and top-down plots).
# usage: run_milestone3_compare.sh <scene> [--adapter <controller_dir>] [--route <commands.jsonl>] [--label name]
set -euo pipefail
# The whole launcher runs inside main() so bash parses the complete file before executing it.
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scene=${1:?scene}; shift
adapter=""; route="$project_root/config/milestone3-compare-route.jsonl"; label=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --adapter) adapter=$2; shift 2 ;;
        --route) route=$2; shift 2 ;;
        --label) label=$2; shift 2 ;;
        *) echo "Unknown argument $1" >&2; exit 2 ;;
    esac
done
if [[ -z "$adapter" ]]; then
    adapter=$(ls -d "$project_root"/artifacts/milestone3/train-rlft-m3_rlft_walk_seed0-*/results/m3_rlft_walk_seed0 2>/dev/null | head -1)
fi
[[ -n "$adapter" && -f "$adapter/inference_last.ckpt" ]] || { echo "No adapter controller found; pass --adapter" >&2; exit 2; }
route=$(readlink -f "$route")
[[ -f "$route" ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="compare-$scene${label:+-$label}"
evidence="$project_root/diagnostics/$stamp-milestone3-$name"
output="$project_root/artifacts/milestone3/$name-$stamp"
mkdir -p "$evidence" "$output"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
cp "$route" "$evidence/route.jsonl"
cp "$project_root/scripts/run_milestone3_compare.sh" "$project_root/scripts/compare_sessions.py" "$evidence/"
printf '{"scene": "%s", "adapter": "%s", "route": "%s", "started_utc": "%s", "output": "%s"}\n' "$scene" "$adapter" "$route" "$stamp" "$output" > "$evidence/compare-contract.json"
printf '{"output": "%s", "evidence": "%s", "launcher_pid": %s, "started_utc": "%s"}\n' "$output" "$evidence" "$$" "$stamp" > "$project_root/.runtime/studio-compare-current.json"
declare -A session_dir
for side in tracker adapter; do
    before=$(ls -td "$project_root"/artifacts/milestone3/live-*-"$scene"-* 2>/dev/null | head -1 || true)
    if [[ $side == tracker ]]; then
        "$project_root/scripts/run_milestone3_live.sh" tracker "$route" --scene "$scene" --label "cmp${label:+-$label}"
    else
        "$project_root/scripts/run_milestone3_live.sh" "$adapter" "$route" --scene "$scene" --label "cmp${label:+-$label}"
    fi
    latest=$(ls -td "$project_root"/artifacts/milestone3/live-*-"$scene"-* 2>/dev/null | head -1)
    [[ -n "$latest" && "$latest" != "$before" ]] || { echo "STOP: no new session folder for $side" >&2; exit 4; }
    session_dir[$side]=$latest
    echo "$side session: $latest"
done
python3 -I "$project_root/scripts/compare_sessions.py" --left "${session_dir[tracker]}" --right "${session_dir[adapter]}" --out "$output" \
    --left-name "tracker-driven walker" --right-name "learned adapter"
cp "$output/comparison.json" "$output/comparison.md" "$output/topdowns.png" "$evidence/"
printf '{"tracker": "%s", "adapter": "%s", "output": "%s", "video": "%s"}\n' "${session_dir[tracker]}" "${session_dir[adapter]}" "$output" "$output/side-by-side.mp4" > "$evidence/sessions.json"
cp "$evidence/sessions.json" "$output/sessions.json"
echo "Comparison recorded. Output: $output Evidence: $evidence"
}

main "$@"
exit $?
