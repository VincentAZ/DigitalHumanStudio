#!/usr/bin/env bash
# Official Isaac checker only. A pass does not replace physics/render smoke tests.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker_cmd="$project_root/scripts/docker.sh"
evidence="$project_root/diagnostics/$(date -u +%Y%m%dT%H%M%S)-isaac"
mkdir -p "$evidence"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
"$docker_cmd" info > "$evidence/docker-info.txt"
image=nvcr.io/nvidia/isaac-sim:6.0.0
lock_file="$project_root/config/isaac-image.lock"
if [[ -f "$lock_file" ]]; then
    image=$(cat "$lock_file")
    [[ "$image" =~ ^nvcr.io/nvidia/isaac-sim@sha256:[a-f0-9]{64}$ ]] || {
        echo 'Invalid Isaac image digest lock; inspect before continuing.'
        exit 2
    }
fi
"$docker_cmd" pull "$image"
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
image_digest=$("$docker_cmd" image inspect --format '{{index .RepoDigests 0}}' "$image")
printf '%s\n' "$image_digest" > "$evidence/image-digest.txt"
printf '%s\n' "$image_digest" > "$lock_file"
"$docker_cmd" run --rm --entrypoint bash "$image_digest" -lc 'cat /etc/os-release; python3 --version' \
    > "$evidence/container-userspace.txt"
if ! grep -q '^VERSION_ID="24.04"$' "$evidence/container-userspace.txt"; then
    echo 'STOP: image userspace does not match the requested Ubuntu 24.04 baseline.'
    exit 3
fi
"$docker_cmd" run --rm --gpus all --runtime=nvidia --entrypoint nvidia-smi "$image_digest" \
    > "$evidence/container-gpu.txt"
for attempt in 1 2; do
    container_name="studio-check-$(date -u +%s)-$attempt"
    # Keep the stopped container until its logs have been copied to the evidence directory.
    set +e
    timeout --signal=TERM --kill-after=15s 300 "$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia \
        --env ACCEPT_EULA=Y --entrypoint bash "$image_digest" \
        -lc './isaac-sim.compatibility_check.sh --/app/quitAfter=10 --no-window' \
        2>&1 | tee "$evidence/check-$attempt.log"
    result=${PIPESTATUS[0]}
    set -e
    printf '%s\n' "$result" > "$evidence/check-$attempt.exit-code.txt"
    if [[ $result -ne 0 ]]; then
        "$docker_cmd" stop --time 20 "$container_name" || true
    fi
    "$docker_cmd" cp "$container_name:/isaac-sim/.nvidia-omniverse/logs" \
        "$evidence/kit-logs-$attempt" || true
    "$docker_cmd" inspect "$container_name" > "$evidence/container-$attempt.json"
    "$docker_cmd" rm "$container_name"
    if [[ $result -ne 0 ]] || ! grep -q 'System checking result: PASSED' "$evidence/check-$attempt.log"; then
        echo 'STOP: Isaac compatibility was not established. Preserve diagnostics and review before further setup.'
        exit 4
    fi
done
echo 'Official checker passed twice. Physics, rendered image, and pinned learning-stack checks remain required.'
