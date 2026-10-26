#!/usr/bin/env bash
# CPU-only check; never starts Isaac or reads the bundled motion data.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$project_root/diagnostics/$stamp-milestone1-preflight"
mkdir -p "$evidence"
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
cp "$project_root/scripts/milestone1_preflight.py" "$project_root/scripts/check_milestone1_preflight.sh" "$project_root/config/milestone1-assets.lock.json" "$evidence/"
python3 - "$project_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / 'config/milestone1-assets.lock.json').read_text())
for record in manifest['files']:
    path = root / manifest['asset_root'] / record['path']
    assert path.stat().st_size == record['bytes'], path
    with path.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'], path
print('All staged asset hashes match the lock.')
PY
command=("$project_root/scripts/docker.sh" run --rm --user "$(id -u):$(id -g)"
    --env OMP_NUM_THREADS=4
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$project_root/.runtime/milestone1/assets,dst=/studio/assets,readonly"
    --mount "type=bind,src=$evidence,dst=/studio/output"
    "$image" /studio/scripts/milestone1_preflight.py --assets /studio/assets --output /studio/output)
printf '%q ' "${command[@]}" > "$evidence/command.txt"
printf '\n' >> "$evidence/command.txt"
"${command[@]}"
echo "CPU-only contract evidence: $evidence"
