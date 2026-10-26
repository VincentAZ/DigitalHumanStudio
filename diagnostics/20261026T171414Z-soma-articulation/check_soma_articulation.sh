#!/usr/bin/env bash
# Independent M1 physical-asset probe; no motion data or model weights are mounted.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$project_root/diagnostics/$stamp-soma-articulation"
output="$project_root/artifacts/milestone1/articulation-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
assets="$project_root/.runtime/milestone1/assets"
mkdir -p "$evidence" "$output" "$runtime_home"
exec 9>"$project_root/.runtime/studio-gpu.lock"
flock -n 9 || { echo 'Another studio GPU job holds the lock.' >&2; exit 2; }
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
cp "$project_root/scripts/soma_articulation_probe.py" "$project_root/scripts/check_soma_articulation.sh" "$project_root/config/milestone1-assets.lock.json" "$evidence/"
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
"$docker_cmd" ps --format '{{.Names}} {{.Status}}' > "$evidence/running-containers-before.txt"
if [[ -s "$evidence/running-containers-before.txt" ]]; then
    echo 'STOP: inspect running containers before starting the GPU probe.'
    exit 2
fi
python3 - "$project_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / 'config/milestone1-assets.lock.json').read_text())
for record in manifest['files']:
    if record['path'].startswith('protomotions/data/assets/') or record['path'] == 'data/pretrained_models/motion_tracker/soma-bones/resolved_configs_inference.pt':
        path = root / manifest['asset_root'] / record['path']
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], path
print('Physical asset and serialized configuration hashes verified; no motion data accessed.')
PY
container_name="studio-soma-articulation-$stamp"
command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
    --workdir /studio/output
    --user "$(id -u):$(id -g)"
    --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES --env NVIDIA_DRIVER_CAPABILITIES=all
    --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
    --env XDG_CONFIG_HOME=/studio-home/.config --env XDG_DATA_HOME=/studio-home/.local/share
    --env HUB__CACHE__PATH=/studio-home/hub-cache --env PROTOMOTIONS_ASSET_ROOT=/studio/assets
    --mount "type=bind,src=$runtime_home,dst=/studio-home"
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$assets/protomotions/data/assets,dst=/studio/assets,readonly"
    --mount "type=bind,src=$assets/data/pretrained_models/motion_tracker/soma-bones/resolved_configs_inference.pt,dst=/studio/config.pt,readonly"
    --mount "type=bind,src=$output,dst=/studio/output"
    "$image" /studio/scripts/soma_articulation_probe.py --output /studio/output --device cuda:0 --viz none
    --kit_args "--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log")
{ printf '%q' "${command[0]}"; printf ' %q' "${command[@]:1}"; printf '\n'; } > "$evidence/command.txt"
set +e
timeout --signal=TERM --kill-after=30s 900 "${command[@]}" 2>&1 | tee "$evidence/run.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$evidence/process-exit-code.txt"
if [[ $result -ne 0 ]]; then "$docker_cmd" stop --time 20 "$container_name" || true; fi
"$docker_cmd" inspect "$container_name" > "$evidence/container.json"
for record in requested-config.json actual-mapping.json synthetic-reset.json result.json kit.log; do
    if [[ -f "$output/$record" ]]; then cp "$output/$record" "$evidence/$record"; fi
done
validation=0
python3 - "$output" "$result" "$evidence" <<'PY' || validation=$?
import hashlib, json, sys
from pathlib import Path
output, code, evidence = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
report = json.loads((output / 'result.json').read_text()) if (output / 'result.json').exists() else {}
log = (output / 'kit.log').read_text(errors='replace') if (output / 'kit.log').exists() else ''
cleanup = all(s in log for s in ['SimulationApp.close: Replicator shutdown finished', 'Simulation App Shutting Down', 'SimulationApp.close: shutting down app'])
accepted = (code == 0 and report.get('status') == 'checks_passed_shutdown_pending'
    and report.get('scope') == 'articulation_adapter_only' and report.get('finite_samples') == 30
    and report.get('shutdown', {}).get('stage_closed') is True and cleanup)
artifacts = {}
for path in output.rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            artifacts[str(path.relative_to(output))] = {'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
(evidence / 'artifact-manifest.json').write_text(json.dumps({'root': str(output), 'files': artifacts}, indent=2) + '\n')
(evidence / 'outcome.json').write_text(json.dumps({'status': 'passed' if accepted else 'failed', 'process_exit_code': code, 'cleanup_logged': cleanup, 'milestone1_complete': False}, indent=2) + '\n')
sys.exit(0 if accepted else 4)
PY
if [[ $validation -ne 0 ]]; then
    printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
    echo "STOP: SOMA articulation probe failed. Evidence: $evidence"
    exit 4
fi
"$docker_cmd" rm "$container_name"
echo "SOMA articulation probe passed; motion tracking is still untested. Evidence: $evidence"
