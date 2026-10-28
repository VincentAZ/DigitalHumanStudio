#!/usr/bin/env bash
# Build (or rebuild) the shipped skill catalog on the CPU inside the pinned image.
# usage: build_skill_catalog.sh [--no-gif]
set -euo pipefail
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
assets="$project_root/.runtime/milestone1/assets"
[[ -f "$assets/data/motion_for_trackers/soma23_bones_seed_mini.pt" ]] || { echo "Milestone 1 assets missing: run scripts/fetch_milestone1_assets.py" >&2; exit 2; }
mkdir -p "$project_root/skills"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
evidence="$project_root/diagnostics/$stamp-skill-catalog"
mkdir -p "$evidence"
"$docker_cmd" run --rm --user "$(id -u):$(id -g)" --env PYTHONPATH=/studio/scripts \
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly" \
    --mount "type=bind,src=$assets,dst=/studio/assets,readonly" \
    --mount "type=bind,src=$project_root/config,dst=/studio/config,readonly" \
    --mount "type=bind,src=$project_root/skills,dst=/studio/skills" \
    "$image" /studio/scripts/build_skill_catalog.py --assets /studio/assets --config /studio/config --skills /studio/skills "$@" \
    2>&1 | tee "$evidence/build.log"
cp "$project_root/skills/shipped-catalog.json" "$evidence/"
echo "Catalog built. Evidence: $evidence"
}
main "$@"
