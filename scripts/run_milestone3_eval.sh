#!/usr/bin/env bash
# One recorded Milestone 3 evaluation process on the reserved scenarios.
# usage: run_milestone3_eval.sh <adapter|prior> <set: flat|redirect|push> <controller_dir> [--record <trial ids>] [--env-config <dir>] [--seed N] [--label x] [--temperature T]
#   controller_dir holds inference_last.ckpt and resolved_configs_inference.pt (adapter) or supplies the task
#   environment configuration for the unadapted prior baseline.
set -euo pipefail
# The whole launcher runs inside main() so bash parses the complete file before executing it:
# editing this script while a session is running can then no longer corrupt that session.
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
controller=${1:?controller}; scenario_set=${2:?set}; controller_dir=${3:?controller_dir}
shift 3
record_ids=""; env_config_dir=""; seed=0; label=""; temperature=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --record) record_ids=$2; shift 2 ;;
        --env-config) env_config_dir=$2; shift 2 ;;
        --seed) seed=$2; shift 2 ;;
        --label) label=$2; shift 2 ;;
        --temperature) temperature=$2; shift 2 ;;
        *) echo "Unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ "$controller" == adapter || "$controller" == prior ]] || { echo 'Expected adapter or prior' >&2; exit 2; }
[[ "$scenario_set" == flat || "$scenario_set" == redirect || "$scenario_set" == push ]]
controller_dir=$(cd -- "$controller_dir" && pwd)
[[ -z "$env_config_dir" ]] && env_config_dir=$controller_dir
env_config_dir=$(cd -- "$env_config_dir" && pwd)
[[ -f "$env_config_dir/resolved_configs_inference.pt" ]] || { echo "Missing resolved_configs_inference.pt in $env_config_dir" >&2; exit 2; }
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mode=batch; [[ -n "$record_ids" ]] && mode=record
name="$controller-$scenario_set-$mode${label:+-$label}"
evidence="$project_root/diagnostics/$stamp-milestone3-eval-$name"
output="$project_root/artifacts/milestone3/eval-$name-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
assets="$project_root/.runtime/milestone1/assets"
mkdir -p "$evidence" "$output" "$runtime_home"
exec 9>"$project_root/.runtime/studio-gpu.lock"
flock -n 9 || { echo 'Another studio GPU job holds the lock.' >&2; exit 2; }
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
cp -r "$project_root/scripts/studio_walk" "$evidence/studio_walk"; rm -rf "$evidence/studio_walk/__pycache__"
cp "$project_root/scripts/milestone3_eval.py" "$project_root/scripts/run_milestone3_eval.sh" "$project_root/scripts/verify_milestone1_outputs.py" \
   "$project_root/config/milestone3-scenarios.json" "$project_root/config/milestone1-assets.lock.json" "$project_root/config/milestone1-license.json" "$evidence/"
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
"$docker_cmd" ps --format '{{.Names}} {{.Status}}' > "$evidence/running-containers-before.txt"
[[ ! -s "$evidence/running-containers-before.txt" ]] || { echo 'STOP: inspect running containers first.'; exit 2; }
python3 - "$project_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1])
assert json.loads((root/'config/milestone1-license.json').read_text())['eligibility_status']=='confirmed_by_user'
manifest=json.loads((root/'config/milestone1-assets.lock.json').read_text())
for record in manifest['files']:
    path=root/manifest['asset_root']/record['path']
    assert path.stat().st_size==record['bytes'],path
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream,'sha256').hexdigest()==record['sha256'],path
print('All pinned assets verified; user eligibility statement recorded.')
PY
( cd "$controller_dir" && sha256sum inference_last.ckpt resolved_configs_inference.pt 2>/dev/null ) > "$evidence/controller.sha256" || true
container_name="studio-m3-eval-$name-$stamp"
eval_args=(--output /studio/output --controller "$controller" --set "$scenario_set" --seed "$seed"
    --scenarios /studio/scenarios.json --env-config /studio/env-config/resolved_configs_inference.pt
    --prior-checkpoint /studio/assets/data/pretrained_models/gpc_prior/soma_bones/inference_last.ckpt)
[[ "$controller" == adapter ]] && eval_args+=(--adapter-checkpoint /studio/controller/inference_last.ckpt)
[[ -n "$temperature" ]] && eval_args+=(--temperature "$temperature")
kit_args="--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log --/log/level=Info"
launcher_args=(--device cuda:0 --viz none)
if [[ -n "$record_ids" ]]; then eval_args+=(--record --trial-ids "$record_ids"); launcher_args+=(--enable_cameras); fi
command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
    --workdir /studio/output --user "$(id -u):$(id -g)" --shm-size=4g
    --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES --env NVIDIA_DRIVER_CAPABILITIES=all
    --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
    --env XDG_CONFIG_HOME=/studio-home/.config --env XDG_DATA_HOME=/studio-home/.local/share
    --env HUB__CACHE__PATH=/studio-home/hub-cache --env PROTOMOTIONS_ASSET_ROOT=/studio/assets/protomotions/data/assets
    --env PYTHONPATH=/studio/scripts --env OMP_NUM_THREADS=4
    --mount "type=bind,src=$runtime_home,dst=/studio-home"
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$assets,dst=/studio/assets,readonly"
    --mount "type=bind,src=$controller_dir,dst=/studio/controller,readonly"
    --mount "type=bind,src=$env_config_dir,dst=/studio/env-config,readonly"
    --mount "type=bind,src=$project_root/config/milestone3-scenarios.json,dst=/studio/scenarios.json,readonly"
    --mount "type=bind,src=$output,dst=/studio/output"
    "$image" /studio/scripts/milestone3_eval.py "${eval_args[@]}" "${launcher_args[@]}" --kit_args "$kit_args")
{ printf '%q' "${command[0]}"; printf ' %q' "${command[@]:1}"; printf '\n'; } > "$evidence/command.txt"
set +e
timeout --signal=TERM --kill-after=30s 7200 "${command[@]}" 2>&1 | tee "$evidence/run.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$evidence/process-exit-code.txt"
if [[ $result -ne 0 ]]; then "$docker_cmd" stop --timeout 20 "$container_name" >/dev/null 2>&1 || true; fi
"$docker_cmd" inspect "$container_name" > "$evidence/container.json"
media_result=0
if [[ -n "$record_ids" && $result -eq 0 && -f "$output/result.json" ]]; then
    media_result=1
    set +e
    "$docker_cmd" run --rm --user "$(id -u):$(id -g)" --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly" \
        --mount "type=bind,src=$output,dst=/studio/output" "$image" /studio/scripts/verify_milestone1_outputs.py > "$evidence/media.log" 2>&1
    media_result=$?
    set -e
fi
printf '%s\n' "$media_result" > "$evidence/media-exit-code.txt"
for record in run-contract.json resolved-configs.json trials.json measurements.json result.json media-validation.json kit.log; do
    [[ -f "$output/$record" ]] && cp "$output/$record" "$evidence/$record"
done
cp "$output"/topdown-*.png "$evidence/" 2>/dev/null || true
validation=0
python3 - "$output" "$result" "$media_result" "$evidence" "$controller" "$scenario_set" <<'PY' || validation=$?
import hashlib, json, sys
from pathlib import Path
output,code,media_code,evidence,controller,scenario_set=Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]),Path(sys.argv[4]),sys.argv[5],sys.argv[6]
report=json.loads((output/'result.json').read_text()) if (output/'result.json').exists() else {}
log=(output/'kit.log').read_text(errors='replace') if (output/'kit.log').exists() else ''
cleanup=all(s in log for s in ['SimulationApp.close: Replicator shutdown finished','Simulation App Shutting Down','SimulationApp.close: shutting down app'])
accepted=(code==0 and media_code==0 and cleanup and report.get('status')=='checks_passed_shutdown_pending'
    and report.get('controller')==controller and report.get('set')==scenario_set
    and report.get('all_trials_complete') is True and report.get('all_sampled_states_actions_finite') is True
    and report.get('shutdown',{}).get('simulation_context_cleared') is True)
artifacts={}
for path in output.rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            artifacts[str(path.relative_to(output))]={'bytes':path.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
(evidence/'artifact-manifest.json').write_text(json.dumps({'root':str(output),'files':artifacts},indent=2)+'\n')
m=report.get('measurements',{})
outcome={'status':'passed' if accepted else 'failed','process_exit_code':code,'media_exit_code':media_code,'cleanup_logged':cleanup,
         'controller':controller,'set':scenario_set,'trials':m.get('trials'),'successes':m.get('successes'),'success_rate':m.get('success_rate'),
         'gate_passed_90_percent':m.get('gate_passed_90_percent'),'milestone3_complete':False}
(evidence/'outcome.json').write_text(json.dumps(outcome,indent=2)+'\n')
print(json.dumps(outcome,indent=2))
sys.exit(0 if accepted else 4)
PY
if [[ $validation -ne 0 ]]; then
    printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
    echo "STOP: evaluation process failed its runtime/evidence gate (this is about the run, not the controller's score). Evidence: $evidence"
    exit 4
fi
"$docker_cmd" rm "$container_name" >/dev/null
echo "Recorded evaluation run accepted. Evidence: $evidence"
}

main "$@"
