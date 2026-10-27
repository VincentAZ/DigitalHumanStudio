# Control center

`scripts/studio.sh` launches the Digital Human Studio control center: one desktop window
(PySide6 on the host) from which you train, inspect results and direct the character. It is the
interface described by the plan's Milestone 3 live controls and Milestone 5 studio views, built
on top of the recorded launchers rather than replacing them. Every simulation, training and
evaluation process still runs inside the locked runtime image through `scripts/run_milestone3_*.sh`,
takes the studio GPU lock and records its evidence under `diagnostics/` exactly as before.

## Launch

```bash
scripts/studio.sh
```

The interface runs in a project-local Python 3.12 environment at `.runtime/studio-app/`
(created by the launcher from `config/studio-app-requirements.txt`, hash-pinned PySide6 6.12.0).
It needs a desktop session (Wayland or X11) and the pinned uv/Python from
`python3 scripts/install_local_tools.py`. Nothing in the Isaac image changed for the interface.

## Views

| View | What you can do |
|---|---|
| Live scene | Pick a trained controller, start an interactive Isaac worker, watch the rendered preview, click the top-down room map to send the character somewhere, stop walking, pause/resume simulated time, reset explicitly, push the character, mark recording segments, end the session. Command acknowledgements and the character state update live. |
| Training | Start a bounded SFT or RLFT job (stage, seed, environments, batch, wall-clock cap, experiment name, warm start), follow every run's epoch metrics as plots, read its session log, request a clean stop after the current epoch, or cancel now. |
| Skills | Every trained adapter with its training outcome and its best accepted reserved-scenario scores; jump to the live scene or to an evaluation with that controller. |
| Evaluation | Start a 100-trial reserved-scenario evaluation (flat, redirect, push; adapter or unadapted prior; optional recorded trials and temperature override) and inspect every past evaluation, its failure reasons, top-down plot and recorded video. |
| Project | Locked image digest, GPU, running containers, studio lock, milestone records, latest progress-log entries, Mixar launch, shortcuts to the plan, log and diagnostics. |

The bottom dock shows the output of launchers started from the window; the full text is also
appended to `.runtime/studio-app.log`. The status bar polls the GPU, the studio lock and the
container list every two seconds.

## How the live scene works

`scripts/run_milestone3_live.sh --interactive` starts `scripts/milestone3_live.py` in the locked
image with `--interactive --live-dir`. The worker then:

- reads `commands.jsonl` from its output directory after every control step and applies each
  new line immediately (the interface appends one JSON line per button press or map click);
- publishes `live/state.json` (simulated time, state, pelvis position and heading, speed,
  distance to target, spawn, destination, resets, recording, measured control steps per wall
  second) and `live/frame.jpg` (the RTX camera frame) atomically after every step;
- treats `pause` without `wall_seconds` as a hold on simulated time until `resume`; while paused it
  keeps reading commands and republishing state, so the interface stays live;
- keeps all of the scripted session's rules: destinations outside the room are rejected, a
  detected fall rejects further destinations until an explicit `reset`, resets return to the
  session's first spawn point, and no invisible reset or teleport exists;
- records `performance.mp4`, `trace.jsonl`, `status.jsonl`, `summary.json` and `topdown.png`
  as before, and the launcher applies the same evidence gate (clean shutdown, frame/step/trace
  counts, exit 0) before accepting the session.

The launcher writes `.runtime/studio-live-current.json` so the interface can find the session's
output and container; reopening the window re-attaches to a running session. `End session` sends
`quit`, which ends the worker cleanly and lets the launcher record the evidence; `Force stop` is a
`docker stop` that the launcher records as a failed session with the container retained.

Preview frames are rendered by the simulation worker itself, so the preview rate is the worker's
control-step rate, not the recording rate: recordings stay timed at 30 fps simulated regardless of
how fast the preview arrives. Larger preview sizes cost render time per step.

## Training and evaluation from the window

The Training view calls `scripts/run_milestone3_train.sh` with the fields shown; the
Evaluation view calls `scripts/run_milestone3_eval.sh`. Both refuse to start while another studio
GPU job holds the lock, and the launchers enforce the same rule themselves. `Stop after this
epoch` writes `STOP_REQUESTED` next to the run's `metrics.jsonl`; the training wrapper treats it
like the wall-clock cap, saves a final `last.ckpt` and exits 0, so the run passes its evidence
gate. `Cancel now` stops the container and the run is recorded as failed, as the plan requires.

## Limits

- The interface is a view over recorded launchers. It does not change acceptance rules; the
  Skills view reports the 90/100 gates from recorded evaluations only.
- The preview is a file-based frame stream from the worker's own camera at the worker's step
  rate; a separate 30 fps 720p preview stream is not implemented.
- Milestone 2 (detailed visual character) and Milestone 4 (second skill, skill switching) are not
  built, so the Skills view lists walking adapters only and the live scene has no skill switch.
