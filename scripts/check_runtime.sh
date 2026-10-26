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
        --mount "type=bind,src=$runtime_home,dst=/studio-home"
        --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
        --mount "type=bind,src=$output,dst=/studio/output"
        "$image" /studio/scripts/runtime_smoke.py
        --output /studio/output --device cuda:0 --enable_cameras --viz none)
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
    if [[ $result -ne 0 ]] || [[ ! -f "$output/result.json" ]]; then
        printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
        echo "STOP: runtime smoke did not pass. Evidence: $evidence; retained: $container_name"
        exit 4
    fi
    # A report alone cannot substitute for the process exiting cleanly.
    python3 - "$output/result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))
assert result['status'] == 'passed', result
assert result['physics_device'] == 'cuda:0', result
assert result['steps'] == 240, result
PY
    cp "$output/result.json" "$evidence/run-$attempt.result.json"
    cp "$output/render.png" "$evidence/run-$attempt.render.png"
    sha256sum "$output/scene.usda" "$output/render.png" "$output/trajectory.json" \
        > "$evidence/run-$attempt.artifact-sha256.txt"
    "$docker_cmd" rm "$container_name"
done
printf '%s\n' "$runtime_home" > "$evidence/persistent-cache-and-log-path.txt"
echo "Pinned runtime smoke passed twice. Evidence: $evidence"
