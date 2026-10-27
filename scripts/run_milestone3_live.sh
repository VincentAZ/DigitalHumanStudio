#!/usr/bin/env bash
# One recorded live-direction session with the trained walking adapter.
# usage: run_milestone3_live.sh <controller_dir|tracker> [<commands.jsonl>] [--label name] [--interactive] [--preview WxH]
#   controller_dir: a trained adapter directory (inference_last.ckpt + resolved_configs_inference.pt), or the word
#   "tracker" for the tracker-driven walker (Milestone 1 tracker following a reference composed from licensed clips).
#   --interactive: the control center appends commands to <output>/commands.jsonl while the worker publishes
#   preview frames to <output>/live/; the session pointer is written to .runtime/studio-live-current.json.
set -euo pipefail
# The whole launcher runs inside main() so bash parses the complete file before executing it:
# editing this script while a session is running can then no longer corrupt that session.
main() {
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
controller_dir=${1:?controller_dir}; shift
commands="$project_root/config/milestone3-live-script.jsonl"; label=""; interactive=0; preview="640x480"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --label) label=$2; shift 2 ;;
        --interactive) interactive=1; shift ;;
        --preview) preview=$2; shift 2 ;;
        *) commands=$1; shift ;;
    esac
done
[[ "$preview" =~ ^[0-9]+x[0-9]+$ ]] || { echo "Expected --preview WxH" >&2; exit 2; }
preview_width=${preview%x*}; preview_height=${preview#*x}
controller=adapter
if [[ "$controller_dir" == tracker ]]; then
    controller=tracker
    controller_dir="$project_root/.runtime/milestone1/assets/data/pretrained_models/motion_tracker/soma-bones"
    [[ -f "$controller_dir/last_lab.ckpt" && -f "$controller_dir/resolved_configs_inference.pt" ]]
else
    controller_dir=$(cd -- "$controller_dir" && pwd)
    [[ -f "$controller_dir/inference_last.ckpt" && -f "$controller_dir/resolved_configs_inference.pt" ]]
fi
[[ $interactive == 1 ]] || commands=$(readlink -f "$commands")
docker_cmd="$project_root/scripts/docker.sh"
image=$(cat "$project_root/config/runtime-image.lock")
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="live${label:+-$label}"; [[ $interactive == 1 ]] && name="live-interactive${label:+-$label}"
[[ $controller == tracker ]] && name="${name/live/live-tracker}"
evidence="$project_root/diagnostics/$stamp-milestone3-$name"
output="$project_root/artifacts/milestone3/$name-$stamp"
runtime_home="$project_root/.runtime/isaac-home"
assets="$project_root/.runtime/milestone1/assets"
mkdir -p "$evidence" "$output" "$runtime_home"
if [[ $interactive == 1 ]]; then
    commands="$output/commands.jsonl"; : > "$commands"; mkdir -p "$output/live"
fi
exec 9>"$project_root/.runtime/studio-gpu.lock"
flock -n 9 || { echo 'Another studio GPU job holds the lock.' >&2; exit 2; }
exec > >(tee "$evidence/session.log") 2>&1
trap 'result=$?; printf "%s\n" "$result" > "$evidence/exit-code.txt"' EXIT
container_name="studio-m3-$name-$stamp"
if [[ $interactive == 1 ]]; then
    printf '{"output": "%s", "evidence": "%s", "container": "%s", "launcher_pid": %s, "controller_dir": "%s", "started_utc": "%s"}\n' \
        "$output" "$evidence" "$container_name" "$$" "$controller_dir" "$stamp" > "$project_root/.runtime/studio-live-current.json"
fi
cp -r "$project_root/scripts/studio_walk" "$evidence/studio_walk"; rm -rf "$evidence/studio_walk/__pycache__"
cp "$project_root/scripts/milestone3_live.py" "$project_root/scripts/run_milestone3_live.sh" "$commands" "$evidence/"
if [[ $controller == tracker ]]; then
    ( cd "$controller_dir" && sha256sum last_lab.ckpt resolved_configs_inference.pt ) > "$evidence/controller.sha256"
else
    ( cd "$controller_dir" && sha256sum inference_last.ckpt resolved_configs_inference.pt ) > "$evidence/controller.sha256"
fi
"$docker_cmd" image inspect "$image" > "$evidence/image.json"
"$docker_cmd" ps --format '{{.Names}} {{.Status}}' > "$evidence/running-containers-before.txt"
[[ ! -s "$evidence/running-containers-before.txt" ]] || { echo 'STOP: inspect running containers first.'; exit 2; }
worker_args=(--max-session-seconds 120)
controller_args=(--controller "$controller")
[[ $controller == adapter ]] && controller_args+=(--adapter-checkpoint /studio/controller/inference_last.ckpt)
mounts=(--mount "type=bind,src=$commands,dst=/studio/commands.jsonl,readonly")
commands_in_container=/studio/commands.jsonl
session_timeout=3600
if [[ $interactive == 1 ]]; then
    worker_args=(--interactive --live-dir /studio/output/live --max-session-seconds 14400
                 --preview-width "$preview_width" --preview-height "$preview_height")
    mounts=(); commands_in_container=/studio/output/commands.jsonl; session_timeout=15000
fi
command=("$docker_cmd" run --name "$container_name" --gpus all --runtime=nvidia
    --workdir /studio/output --user "$(id -u):$(id -g)" --shm-size=2g
    --env ACCEPT_EULA=Y --env OMNI_KIT_ACCEPT_EULA=YES --env NVIDIA_DRIVER_CAPABILITIES=all
    --env HOME=/studio-home --env XDG_CACHE_HOME=/studio-home/.cache
    --env XDG_CONFIG_HOME=/studio-home/.config --env XDG_DATA_HOME=/studio-home/.local/share
    --env HUB__CACHE__PATH=/studio-home/hub-cache --env PROTOMOTIONS_ASSET_ROOT=/studio/assets/protomotions/data/assets
    --env PYTHONPATH=/studio/scripts --env OMP_NUM_THREADS=4
    --mount "type=bind,src=$runtime_home,dst=/studio-home"
    --mount "type=bind,src=$project_root/scripts,dst=/studio/scripts,readonly"
    --mount "type=bind,src=$assets,dst=/studio/assets,readonly"
    --mount "type=bind,src=$controller_dir,dst=/studio/controller,readonly"
    "${mounts[@]}"
    --mount "type=bind,src=$output,dst=/studio/output"
    "$image" /studio/scripts/milestone3_live.py --output /studio/output
    "${controller_args[@]}" --commands "$commands_in_container"
    "${worker_args[@]}" --device cuda:0 --enable_cameras --viz none
    --kit_args "--portable --portable-root /studio-home/kit --/log/file=/studio/output/kit.log --/log/level=Info")
{ printf '%q' "${command[0]}"; printf ' %q' "${command[@]:1}"; printf '\n'; } > "$evidence/command.txt"
set +e
timeout --signal=TERM --kill-after=30s "$session_timeout" "${command[@]}" 2>&1 | tee "$evidence/run.log"
result=${PIPESTATUS[0]}
set -e
printf '%s\n' "$result" > "$evidence/process-exit-code.txt"
if [[ $result -ne 0 ]]; then "$docker_cmd" stop --timeout 20 "$container_name" >/dev/null 2>&1 || true; fi
"$docker_cmd" inspect "$container_name" > "$evidence/container.json"
for record in session-contract.json summary.json status.jsonl result.json kit.log topdown.png; do
    [[ -f "$output/$record" ]] && cp "$output/$record" "$evidence/$record"
done
[[ $interactive == 1 && -f "$output/commands.jsonl" ]] && cp "$output/commands.jsonl" "$evidence/commands.jsonl"
validation=0
python3 - "$output" "$result" "$evidence" <<'PY' || validation=$?
import hashlib, json, sys
from pathlib import Path
output,code,evidence=Path(sys.argv[1]),int(sys.argv[2]),Path(sys.argv[3])
report=json.loads((output/'result.json').read_text()) if (output/'result.json').exists() else {}
summary=json.loads((output/'summary.json').read_text()) if (output/'summary.json').exists() else {}
log=(output/'kit.log').read_text(errors='replace') if (output/'kit.log').exists() else ''
cleanup=all(s in log for s in ['SimulationApp.close: Replicator shutdown finished','Simulation App Shutting Down','SimulationApp.close: shutting down app'])
trace_lines=sum(1 for _ in (output/'trace.jsonl').open()) if (output/'trace.jsonl').exists() else 0
accepted=(code==0 and cleanup and report.get('status')=='checks_passed_shutdown_pending' and report.get('frames')==report.get('steps')==trace_lines
    and report.get('shutdown',{}).get('simulation_context_cleared') is True and summary.get('commands'))
artifacts={}
for path in output.rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            artifacts[str(path.relative_to(output))]={'bytes':path.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
(evidence/'artifact-manifest.json').write_text(json.dumps({'root':str(output),'files':artifacts},indent=2)+'\n')
results={c['command'].get('cmd'):c.get('result') for c in summary.get('commands',[])}
outcome={'status':'passed' if accepted else 'failed','process_exit_code':code,'cleanup_logged':cleanup,'steps':report.get('steps'),
         'frames':report.get('frames'),'trace_lines':trace_lines,'commands':len(summary.get('commands',[])),
         'command_results':[{'cmd':c['command'].get('cmd'),'at':c['command'].get('at'),'result':c.get('result'),'ack_latency_ms':round(c.get('ack_latency_ms',0),3)} for c in summary.get('commands',[])],
         'final_state':summary.get('final_state'),'resets':summary.get('resets'),'milestone3_complete':False}
(evidence/'outcome.json').write_text(json.dumps(outcome,indent=2)+'\n')
print(json.dumps(outcome,indent=2))
sys.exit(0 if accepted else 4)
PY
if [[ $validation -ne 0 ]]; then
    printf '%s\n' "$container_name" > "$evidence/retained-container.txt"
    echo "STOP: live session failed its runtime/evidence gate. Evidence: $evidence"
    exit 4
fi
"$docker_cmd" rm "$container_name" >/dev/null
echo "Recorded live session accepted. Evidence: $evidence"
}

main "$@"
