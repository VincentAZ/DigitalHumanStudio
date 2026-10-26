#!/usr/bin/env bash
# One recorded Milestone 3 training process (SFT bootstrap or RLFT) in the locked runtime image.
# usage: run_milestone3_train.sh <sft|rlft> <seed> <num_envs> <batch_size> <wall_clock_seconds> <experiment_name>
#        [--warm-start <host path to last.ckpt>] [-- <extra train_agent arguments>]
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stage=${1:?stage}; seed=${2:?seed}; num_envs=${3:?num_envs}; batch_size=${4:?batch_size}
wall_seconds=${5:?wall_clock_seconds}; experiment_name=${6:?experiment_name}
shift 6
warm_start=""
extra_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --warm-start) warm_start=$2; shift 2 ;;
        --) shift; extra_args=("$@"); break ;;
        *) echo "Unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ "$stage" == sft || "$stage" == rlft ]] || { echo 'Expected sft or rlft' >&2; exit 2; }
[[ "$seed" =~ ^[0-9]+$ && "$num_envs" =~ ^[0-9]+$ && "$batch_size" =~ ^[0-9]+$ && "$wall_seconds" =~ ^[0-9]+$ ]]
[[ "$experiment_name" =~ ^[A-Za-z0-9_.-]+$ ]]
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$project_root/diagnostics/$stamp-milestone3-train-$stage"
output="$project_root/artifacts/milestone3/train-$stage-$experiment_name-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
assets="$project_root/.runtime/milestone1/assets"
mkdir -p "$evidence" "$output" "$runtime_home"
exec 9>"$project_root/.runtime/studio-gpu.lock"
flock -n 9 || { echo 'Another studio GPU job holds the lock.' >&2; exit 2; }
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
cp -r "$project_root/scripts/studio_walk" "$evidence/studio_walk"
rm -rf "$evidence/studio_walk/__pycache__"
cp "$project_root/scripts/milestone3_train.py" "$project_root/scripts/run_milestone3_train.sh" \
   "$project_root/config/milestone1-assets.lock.json" "$project_root/config/milestone1-license.json" "$evidence/"
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
"$docker_cmd" ps --format '{{.Names}} {{.Status}}' > "$evidence/running-containers-before.txt"
[[ ! -s "$evidence/running-containers-before.txt" ]] || { echo 'STOP: inspect running containers first.'; exit 2; }
python3 - "$project_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1])
license_record=json.loads((root/'config/milestone1-license.json').read_text())
assert license_record['eligibility_status']=='confirmed_by_user'
manifest=json.loads((root/'config/milestone1-assets.lock.json').read_text())
for record in manifest['files']:
    path=root/manifest['asset_root']/record['path']
    assert path.stat().st_size==record['bytes'],path
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==record['sha256'],path
print('All pinned assets verified; user eligibility statement recorded.')
PY
container_name="studio-m3-train-$stage-$stamp"
mounts=(--mount "type=bind,src=$runtime_home,dst=/studio-home"
        --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
        --mount "type=bind,src=$assets,dst=/studio/assets,readonly"
        --mount "type=bind,src=$output,dst=/studio/output")
train_args=(--robot-name soma23 --simulator isaaclab --num-envs "$num_envs" --batch-size "$batch_size"
    --motion-file /studio/assets/data/motion_for_trackers/soma23_bones_seed_mini.pt
    --experiment-path "/studio/scripts/studio_walk/experiment_$stage.py"
    --experiment-name "$experiment_name" --seed "$seed" --headless True
    --prior-checkpoint /studio/assets/data/pretrained_models/gpc_prior/soma_bones/inference_last.ckpt)
if [[ -n "$warm_start" ]]; then
    [[ -f "$warm_start" ]] || { echo "Warm-start checkpoint missing: $warm_start" >&2; exit 2; }
    warm_dir=$(cd -- "$(dirname -- "$warm_start")" && pwd)
    mounts+=(--mount "type=bind,src=$warm_dir,dst=/studio/warm-start,readonly")
    train_args+=(--checkpoint "/studio/warm-start/$(basename -- "$warm_start")")
    sha256sum "$warm_start" > "$evidence/warm-start.sha256"
fi
command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
    --workdir /studio/output --user "$(id -u):$(id -g)" --shm-size=8g
    --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES --env NVIDIA_DRIVER_CAPABILITIES=all
    --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
    --env XDG_CONFIG_HOME=/studio-home/.config --env XDG_DATA_HOME=/studio-home/.local/share
    --env HUB__CACHE__PATH=/studio-home/hub-cache --env PROTOMOTIONS_ASSET_ROOT=/studio/assets/protomotions/data/assets
    --env PYTHONPATH=/studio/scripts --env OMP_NUM_THREADS=8 --env WANDB_MODE=disabled
    "${mounts[@]}"
    "$image" /studio/scripts/milestone3_train.py
    --wall-clock-limit-seconds "$wall_seconds" --metrics-log /studio/output/metrics.jsonl
    --kit-args "--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log --/log/level=Warn"
    "${train_args[@]}" "${extra_args[@]}")
{ printf '%q' "${command[0]}"; printf ' %q' "${command[@]:1}"; printf '\n'; } > "$evidence/command.txt"
python3 - "$evidence/train-contract.json" "$stage" "$seed" "$num_envs" "$batch_size" "$wall_seconds" "$experiment_name" "$warm_start" "$image" "$output" <<'PY'
import json, sys
keys=['stage','seed','num_envs','batch_size','wall_clock_seconds','experiment_name','warm_start_checkpoint','image','output']
json.dump(dict(zip(keys, sys.argv[2:])) | {'control_hz': 30, 'physics_hz': 120, 'training_performed': True}, open(sys.argv[1],'w'), indent=2)
PY
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu --format=csv -l 30 > "$evidence/gpu-samples.csv" 2>/dev/null &
sampler_pid=$!
set +e
timeout --signal=TERM --kill-after=60s "$((wall_seconds + 1800))" "${command[@]}" 2>&1 | tee "$evidence/run.log"
result=${PIPESTATUS[0]}
set -e
kill "$sampler_pid" 2>/dev/null || true
printf '%s\n' "$result" > "$evidence/process-exit-code.txt"
if [[ $result -ne 0 ]]; then "$docker_cmd" stop --timeout 20 "$container_name" >/dev/null 2>&1 || true; fi
"$docker_cmd" inspect "$container_name" > "$evidence/container.json"
results_dir="$output/results/$experiment_name"
for record in config.yaml resolved_configs.yaml resolved_configs_inference.yaml experiment_config.py; do
    [[ -f "$results_dir/$record" ]] && cp "$results_dir/$record" "$evidence/$record"
done
[[ -f "$output/metrics.jsonl" ]] && cp "$output/metrics.jsonl" "$evidence/metrics.jsonl"
[[ -f "$output/kit.log" ]] && cp "$output/kit.log" "$evidence/kit.log"
( cd "$output" && find results -maxdepth 2 -name '*.ckpt' -print0 | xargs -0 -r sha256sum ) > "$evidence/checkpoints.sha256" || true
validation=0
python3 - "$evidence" "$results_dir" "$result" "$stage" <<'PY' || validation=$?
import json, sys
from pathlib import Path
evidence, results, code, stage = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
metrics = [json.loads(l) for l in (evidence/'metrics.jsonl').read_text().splitlines()] if (evidence/'metrics.jsonl').exists() else []
last = metrics[-1] if metrics else {}
outcome = {'status': 'passed' if code == 0 and (results/'last.ckpt').exists() and (results/'inference_last.ckpt').exists() and metrics else 'failed',
           'process_exit_code': code, 'stage': stage, 'epochs_completed': len(metrics),
           'elapsed_seconds': last.get('elapsed_seconds'), 'last_epoch_fps': last.get('times/fps_last_epoch'),
           'max_gpu_memory_gib': max((m.get('max_gpu_memory_gib') or 0) for m in metrics) if metrics else None,
           'last_ckpt': str(results/'last.ckpt'), 'inference_ckpt': str(results/'inference_last.ckpt'), 'milestone3_complete': False}
(evidence/'outcome.json').write_text(json.dumps(outcome, indent=2)+'\n')
print(json.dumps(outcome, indent=2))
sys.exit(0 if outcome['status']=='passed' else 4)
PY
if [[ $validation -ne 0 ]]; then
    printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
    echo "STOP: $stage training failed its evidence gate. Evidence: $evidence"
    exit 4
fi
"$docker_cmd" rm "$container_name" >/dev/null
echo "Recorded $stage training accepted. Evidence: $evidence Results: $results_dir"
