#!/usr/bin/env bash
# Import a motion file into the skill library on the CPU inside the pinned image.
# usage: import_skill.sh <input .npz|.motion|.pt> <skill id> [import_skill.py options...]
set -euo pipefail
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
input=$(readlink -f "${1:?input file}"); id=${2:?skill id}; shift 2
[[ "$id" =~ ^[a-z][a-z0-9_]{2,47}$ ]] || { echo "skill id must be 3-48 lowercase letters, digits or underscores" >&2; exit 2; }
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
mkdir -p "$project_root/skills"
"$project_root/scripts/docker.sh" run --rm --user "$(id -u):$(id -g)" --env PYTHONPATH=/studio/scripts:/studio/ProtoMotions \
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly" \
    --mount "type=bind,src=$project_root/vendor/ProtoMotions,dst=/studio/ProtoMotions,readonly" \
    --mount "type=bind,src=$(dirname "$input"),dst=/studio/input,readonly" \
    --mount "type=bind,src=$project_root/skills,dst=/studio/skills" \
    "$image" /studio/scripts/import_skill.py --input "/studio/input/$(basename "$input")" --skills /studio/skills --id "$id" "$@"
}
main "$@"
