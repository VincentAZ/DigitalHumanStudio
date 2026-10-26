#!/usr/bin/env bash
# Validate the final pinned learning image twice, retaining failed containers.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid runtime image lock' >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%S)
evidence="$project_root/diagnostics/$stamp-runtime"
artifacts="$project_root/artifacts/milestone0/runtime-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
mkdir -p "$evidence" "$artifacts" "$runtime_home"
printf '%s\n' "$runtime_home" > "$evidence/persistent-cache-and-log-path.txt"
cp "$project_root/scripts/runtime_smoke.py" "$evidence/runtime_smoke.py"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
printf '%s\n' "$image" > "$evidence/image-id.txt"
for attempt in 1 2; do
    output="$artifacts/run-$attempt"
    mkdir -p "$output"
    container_name="studio-runtime-$stamp-$attempt"
    command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
        --user "$(id -u):$(id -g)"
        --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES
        --env NVIDIA_DRIVER_CAPABILITIES=all
        --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
        --env XDG_CONFIG_HOME=/studio-home/.config
        --env XDG_DATA_HOME=/studio-home/.local/share --env HUB__CACHE__PATH=/studio-home/hub-cache
        --mount "type=bind,src=$runtime_home,dst=/studio-home"
        --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
        --mount "type=bind,src=$output,dst=/studio/output"
        "$image" /studio/scripts/runtime_smoke.py
        --output /studio/output --device cuda:0 --enable_cameras --viz none
        --kit_args "--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log" "$@")
    printf '%q ' "${command[@]}" > "$evidence/run-$attempt.command.txt"
    printf '\n' >> "$evidence/run-$attempt.command.txt"
    set +e
    timeout --signal=TERM --kill-after=30s 900 "${command[@]}" 2>&1 | tee "$evidence/run-$attempt.log"
    result=${PIPESTATUS[0]}
    set -e
    printf '%s\n' "$result" > "$evidence/run-$attempt.exit-code.txt"
    if [[ $result -ne 0 ]]; then
        "$docker_cmd" stop --time 20 "$container_name" || true
    fi
    "$docker_cmd" inspect "$container_name" > "$evidence/container-$attempt.json"
    for record in trajectory.json contact-trace.jsonl measurements.json simulation-config.json initial-scene.usda scene.usda result.json render.png; do
        if [[ -f "$output/$record" ]]; then
            cp "$output/$record" "$evidence/run-$attempt.$record"
        fi
    done
    validation=0
    python3 - "$output/result.json" "$result" "$evidence/run-$attempt.outcome.json" <<'PY' || validation=$?
import json, sys
from pathlib import Path
report = Path(sys.argv[1])
child = json.loads(report.read_text()) if report.exists() else None
exit_code = int(sys.argv[2])
accepted = (exit_code == 0 and child is not None
            and child.get('status') == 'checks_passed_cleanup_returned'
            and child.get('physics_device') == 'cuda:0'
            and child.get('physics_hz') in (60, 120)
            and child.get('steps') == 4 * child.get('physics_hz')
            and child.get('duration') == 4.0)
Path(sys.argv[3]).write_text(json.dumps({
    'status': 'passed' if accepted else 'failed', 'process_exit_code': exit_code,
    'child_status': child.get('status') if child else None,
    'note': 'Child assertions and cleanup return cannot replace a successful process exit.',
}, indent=2) + '\n')
sys.exit(0 if accepted else 4)
PY
    if [[ -f "$output/kit.log" ]]; then
        if ! cp "$output/kit.log" "$evidence/run-$attempt.kit.log"; then
            printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
            echo 'STOP: could not preserve runtime Kit logs.'
            exit 5
        fi
    fi
    if [[ $validation -ne 0 ]]; then
        printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
        echo "STOP: runtime smoke did not pass. Evidence: $evidence; retained: $container_name"
        exit 4
    fi
    sha256sum "$output/scene.usda" "$output/render.png" "$output/trajectory.json" \
        > "$evidence/run-$attempt.artifact-sha256.txt"
    "$docker_cmd" rm "$container_name"
done
echo "Pinned runtime smoke passed twice. Evidence: $evidence"
