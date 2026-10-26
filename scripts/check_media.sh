#!/usr/bin/env bash
# Verify the patched recording path without launching a GPU simulation.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid runtime image lock' >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%S)
evidence="$project_root/diagnostics/$stamp-media"
output="$project_root/artifacts/milestone0/media-$stamp"
mkdir -p "$evidence" "$output"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
name="studio-media-$stamp"
command=("$docker_cmd" run --name "$name" --user "$(id -u):$(id -g)" --env HOME=/tmp
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$output,dst=/studio/output"
    "$image" /studio/scripts/media_smoke.py --output /studio/output)
printf '%q ' "${command[@]}" > "$evidence/command.txt"
printf '\n' >> "$evidence/command.txt"
set +e
timeout --signal=TERM --kill-after=20s 120 "${command[@]}"
result=$?
set -e
if [[ $result -ne 0 ]]; then
    "$docker_cmd" stop --time 10 "$name" || true
fi
"$docker_cmd" inspect "$name" > "$evidence/container.json"
if [[ $result -ne 0 ]] || [[ ! -f "$output/media-result.json" ]]; then
    printf '%s\n' "$name" > "$evidence/retained-container.txt"
    echo "Recording test failed; preserve $evidence and $name"
    exit 4
fi
cp "$output/media-result.json" "$evidence/result.json"
sha256sum "$output/recording.mp4" > "$evidence/artifact-sha256.txt"
"$docker_cmd" rm "$name"
echo "Recording encode/decode passed: $evidence"
