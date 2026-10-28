#!/usr/bin/env bash
# Text to skill: generate a SOMA motion with the pinned Kimodo model, convert it with ProtoMotions' SOMA-23
# pipeline and import it into the skill library. Prints the new skill's record as the last stdout line.
# usage: generate_skill.sh --prompt "..." [--seconds 4] [--seed 0] [--name skill_id]
set -euo pipefail
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prompt=""; seconds=4; seed=0; name=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prompt) prompt=$2; shift 2 ;;
        --seconds) seconds=$2; shift 2 ;;
        --seed) seed=$2; shift 2 ;;
        --name) name=$2; shift 2 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
[[ -n "$prompt" ]] || { echo "--prompt is required" >&2; exit 2; }
[[ -x "$project_root/scripts/generate_motion.py" || -f "$project_root/scripts/generate_motion.py" ]] || { echo "scripts/generate_motion.py missing: see docs/MOTION_GENERATION.md" >&2; exit 3; }
[[ -f "$project_root/config/kimodo.lock.json" ]] || { echo "config/kimodo.lock.json missing: the generator is not installed" >&2; exit 3; }
if [[ -z "$name" ]]; then
    name=$(printf '%s' "$prompt" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//' | cut -c1-36)
    [[ "$name" =~ ^[a-z] ]] || name="gen_$name"
    name="${name}_$(date -u +%H%M%S)"
fi
[[ "$name" =~ ^[a-z][a-z0-9_]{2,47}$ ]] || { echo "name must be 3-48 lowercase letters, digits or underscores" >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work="$project_root/artifacts/generation/$stamp-$name"
evidence="$project_root/diagnostics/$stamp-generate-$name"
mkdir -p "$work" "$evidence"
echo "generating '$prompt' ($seconds s, seed $seed) into $work" >&2
"$project_root/scripts/generate_motion.py" --prompt "$prompt" --seconds "$seconds" --seed "$seed" --output "$work" >&2
[[ -f "$work/motion.npz" && -f "$work/generation.json" ]] || { echo "generation produced no motion.npz" >&2; exit 4; }
cp "$work/generation.json" "$evidence/"
licence=$(python3 - "$project_root/config/kimodo.lock.json" <<'PY'
import json, sys
lock = json.load(open(sys.argv[1]))
print(json.dumps({"name": "Generated with " + lock.get("model", {}).get("repo_id", "Kimodo") + " (NVIDIA Open Model License); the generated clip belongs to the user",
                  "url": lock.get("model", {}).get("licence_url", "https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/"),
                  "record": "config/kimodo.lock.json"}))
PY
)
provenance=$(python3 - "$work/generation.json" <<'PY'
import json, sys
g = json.load(open(sys.argv[1]))
keep = {k: g.get(k) for k in ("prompt", "seconds", "seed", "model", "model_revision", "weights_sha256", "diffusion_steps", "cfg_weight", "kimodo_commit", "wall_seconds", "gpu") if k in g}
keep["generation_dir"] = sys.argv[1].rsplit("/", 1)[0]
print(json.dumps(keep))
PY
)
record=$("$project_root/scripts/import_skill.sh" "$work/motion.npz" "$name" --name "$(printf '%s' "$prompt" | cut -c1-60)" \
    --description "Generated from the description \"$prompt\" ($seconds s, seed $seed)." --category generated --tags "generated,text-to-motion" \
    --licence "$licence" --provenance "$provenance" --trim-still 2>"$evidence/import.log" | tail -1)
printf '%s\n' "$record" > "$evidence/skill-record.json"
cp "$project_root/skills/$name/skill.json" "$evidence/"
echo "$record"
}
main "$@"
