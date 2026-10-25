#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%S)
artifacts="$project_root/artifacts/milestone0/mixar-$stamp"
evidence="$project_root/diagnostics/$stamp-mixar"
mkdir -p "$artifacts" "$evidence"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
mixar="$project_root/scripts/mixar.sh"
smoke="$project_root/scripts/mixar_smoke.py"
timeout 180 "$mixar" -b --factory-startup --python-exit-code 1 --python "$smoke" -- create "$artifacts"
timeout 60 "$mixar" -b "$artifacts/milestone0.blend" --python-exit-code 1 --python "$smoke" -- reopen "$artifacts"
timeout 90 "$mixar" "$artifacts/milestone0.blend" --python-exit-code 1 --python "$smoke" -- desktop "$artifacts"
for mode in create reopen desktop; do
    test -f "$artifacts/$mode.json"
    cp "$artifacts/$mode.json" "$evidence/"
done
sha256sum "$artifacts/milestone0.blend" "$artifacts/mixar-preview.png" > "$evidence/artifact-sha256.txt"
printf '%s\n' "$artifacts/milestone0.blend" > "$evidence/project-path.txt"
echo "Mixar save, render, reopen, and desktop checks passed. Evidence: $evidence"
