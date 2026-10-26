#!/usr/bin/env bash
# One recorded baseline process; call again for repeatability, then gpc for the prior.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
family=${1:-tracker}
seed=${2:-0}
[[ "$family" == tracker || "$family" == gpc ]] || { echo 'Expected tracker or gpc' >&2; exit 2; }
[[ "$seed" =~ ^[0-9]+$ ]] || { echo 'Expected integer seed' >&2; exit 2; }
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$project_root/diagnostics/$stamp-milestone1-$family"
output="$project_root/artifacts/milestone1/$family-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
assets="$project_root/.runtime/milestone1/assets"
mkdir -p "$evidence" "$output" "$runtime_home"
exec 9>"$project_root/.runtime/studio-gpu.lock"
flock -n 9 || { echo 'Another studio GPU job holds the lock.' >&2; exit 2; }
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
cp "$project_root/scripts/milestone1_baseline.py" "$project_root/scripts/run_milestone1.sh" "$project_root/scripts/verify_milestone1_outputs.py" "$project_root/config/milestone1-assets.lock.json" "$project_root/config/milestone1-license.json" "$evidence/"
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
container_name="studio-m1-$family-$stamp"
command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
    --workdir /studio/output --user "$(id -u):$(id -g)" --shm-size=2g
    --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES --env NVIDIA_DRIVER_CAPABILITIES=all
    --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
    --env XDG_CONFIG_HOME=/studio-home/.config --env XDG_DATA_HOME=/studio-home/.local/share
    --env HUB__CACHE__PATH=/studio-home/hub-cache --env PROTOMOTIONS_ASSET_ROOT=/studio/assets/protomotions/data/assets
    --env OMP_NUM_THREADS=4
    --mount "type=bind,src=$runtime_home,dst=/studio-home"
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$assets,dst=/studio/assets,readonly"
    --mount "type=bind,src=$project_root/config/milestone1-license.json,dst=/studio/license.json,readonly"
    --mount "type=bind,src=$output,dst=/studio/output"
    "$image" /studio/scripts/milestone1_baseline.py --output /studio/output --family "$family" --seed "$seed"
    --device cuda:0 --enable_cameras --viz none
    --kit_args "--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log --/log/level=Info")
{ printf '%q' "${command[0]}"; printf ' %q' "${command[@]:1}"; printf '\n'; } > "$evidence/command.txt"
set +e
timeout --signal=TERM --kill-after=30s 3600 "${command[@]}" 2>&1 | tee "$evidence/run.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$evidence/process-exit-code.txt"
if [[ $result -ne 0 ]]; then "$docker_cmd" stop --timeout 20 "$container_name" || true; fi
"$docker_cmd" inspect "$container_name" > "$evidence/container.json"
media_result=1
if [[ $result -eq 0 && -f "$output/result.json" ]]; then
    media_command=("$docker_cmd" run --rm --user "$(id -u):$(id -g)"
        --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
        --mount "type=bind,src=$output,dst=/studio/output"
        "$image" /studio/scripts/verify_milestone1_outputs.py)
    { printf '%q' "${media_command[0]}"; printf ' %q' "${media_command[@]:1}"; printf '\n'; } > "$evidence/media-command.txt"
    set +e
    "${media_command[@]}" > "$evidence/media.log" 2>&1
    media_result=$?
    set -e
fi
printf '%s\n' "$media_result" > "$evidence/media-exit-code.txt"
for record in run-contract.json actual-simulator.json resolved-configs.json evaluation-contract.json motion-inventory.json measurements.json trials.json result.json media-validation.json kit.log; do
    if [[ -f "$output/$record" ]]; then cp "$output/$record" "$evidence/$record"; fi
done
validation=0
python3 - "$output" "$result" "$media_result" "$evidence" "$family" <<'PY' || validation=$?
import hashlib, json, sys
from pathlib import Path
output,code,media_code,evidence,family=Path(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]),Path(sys.argv[4]),sys.argv[5]
report=json.loads((output/'result.json').read_text()) if (output/'result.json').exists() else {}
log=(output/'kit.log').read_text(errors='replace') if (output/'kit.log').exists() else ''
cleanup=all(s in log for s in ['SimulationApp.close: Replicator shutdown finished','Simulation App Shutting Down','SimulationApp.close: shutting down app'])
accepted=(code==0 and media_code==0 and cleanup and report.get('status')=='checks_passed_shutdown_pending'
    and report.get('family')==family and report.get('all_trials_complete') is True
    and report.get('all_sampled_states_actions_finite') is True
    and report.get('physics_hz')==120 and report.get('control_hz')==30
    and report.get('shutdown',{}).get('simulation_context_cleared') is True
    and report.get('shutdown',{}).get('stage_closed') is True)
artifacts={}
for path in output.rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            artifacts[str(path.relative_to(output))]={'bytes':path.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
(evidence/'artifact-manifest.json').write_text(json.dumps({'root':str(output),'files':artifacts},indent=2)+'\n')
(evidence/'outcome.json').write_text(json.dumps({'status':'passed' if accepted else 'failed','process_exit_code':code,'media_exit_code':media_code,'cleanup_logged':cleanup,'family':family,'milestone1_complete':False},indent=2)+'\n')
sys.exit(0 if accepted else 4)
PY
if [[ $validation -ne 0 ]]; then
    printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
    echo "STOP: $family baseline failed its runtime/evidence gate. Evidence: $evidence"
    exit 4
fi
"$docker_cmd" rm "$container_name"
echo "Recorded $family baseline accepted. Evidence: $evidence"
