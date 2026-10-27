# Control center

`scripts/studio.sh` launches the Digital Human Studio control center: one desktop window
(PySide6 on the host) from which you direct the character, by hand or through the assistant, in a
scene. It is built on top of the recorded live-session launcher rather than replacing it: every
simulation process runs inside the locked runtime image through `scripts/run_milestone3_live.sh`,
takes the studio GPU lock and records its evidence under `diagnostics/`. Training, evaluation and
the walker-versus-adapter comparison were retired to `sandbox/rl-training/` on 2026-10-27.

## Launch

```bash
scripts/studio.sh
```

The interface runs in a project-local Python 3.12 environment at `.runtime/studio-app/`
(created by the launcher from `config/studio-app-requirements.txt`, hash-pinned PySide6 6.12.0).
It needs a desktop session (Wayland or X11) and the pinned uv/Python from
`python3 scripts/install_local_tools.py`. Nothing in the Isaac image changed for the interface.

`scripts/install_desktop_launcher.sh` installs a desktop entry ("Digital Human Studio" in the
application grid, plus an icon on the Desktop) that runs the same launcher; re-run it after moving
the checkout, or pass `--uninstall`.

## Views

| View | What you can do |
|---|---|
| Live scene | Pick a trained controller, start an interactive Isaac worker, watch the rendered preview, click the top-down room map to send the character somewhere, stop walking, pause/resume simulated time, reset explicitly, push the character, mark recording segments, end the session. Command acknowledgements and the character state update live. |
| Skills | The skill library (today: the tracker-driven walker and the retired trained adapters as controllers; library skills arrive with the next stage). |
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

## Tracker-driven walker

The controller list in the Live scene offers, besides trained adapters, the tracker-driven
walker: the Milestone 1 motion tracker following a reference that `scripts/studio_walk/reference_walker.py`
composes on the fly from licensed clip segments (a looped walk cycle, a walk-to-stand transition and a
standing idle, all from `happy_walk_ff_stop_180_R_005`). The reference heading is steered toward the
clicked destination; the environment re-anchors the reference's planar position to the character
every step, so the tracker always sees one frame ahead of where it is. No learning is involved, and
the clip's own stop produces a true standstill. Launch it outside the window with
`scripts/run_milestone3_live.sh tracker --interactive`. Its sessions are recorded like any other
(`live-tracker-…` folders) and can be compared with the learned adapter in the same room and with the
same buttons.

## Director's assistant

The right-hand dock is a chat with an AI assistant that drives the studio through the same
operations as the buttons: `scripts/studio_assistant/tools.py` defines the tools (describe the studio
and a scene, start or end a live session, walk to a point in scene/world/local frames, stop, pause,
resume, reset, push, mark recordings, wait for arrival or standing, list and play skills) over the
recorded launchers and the live command file, so every assistant action leaves the same evidence as a
button press. Providers: Claude through the Claude Agent SDK (needs an Anthropic API key; Anthropic
does not allow third-party apps to use the claude.ai sign-in), and OpenAI, Google Gemini, xAI Grok and
OpenRouter through one OpenAI-compatible adapter. Keys come from the environment (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`) or from
`~/.config/digital-human-studio/providers.json` (written by the Settings dialog with mode 600); the
repository never holds a key, and no provider is called until you choose one and send a message.
Transcripts with tool calls are saved under `artifacts/assistant/<stamp>-<provider>/`. The same
assistant runs in a terminal: `.runtime/studio-app/bin/python scripts/studio_assistant.py --provider openai "walk to the machine"`.

## Scenes

`scripts/build_scene.py` authors the industrial work-cell scene deterministically as text USD
(`config/scenes/workcell.usda`: walls, a machine with a guarded zone, a conveyor, a rack, two loaded
pallets, lane markings; static PhysX colliders on everything but the markings) together with its
footprint (`workcell.json`: the same boxes in scene-relative metres, the pinned spawn on the flat
terrain, the room size, and the comparison route). The Live scene's Scene picker passes the scene to
the launcher, which references it into the stage at the spawn before the simulation plays, pins the
spawn there, and copies the footprint into the session so the room map and the recorded top-down plot
draw it. Destinations are not planned around obstacles: a click inside the machine sends the character
into the machine. Add a scene by extending the builder or dropping a `<name>.usda` plus `<name>.json`
pair into `config/scenes/`.

## Limits

- The interface is a view over recorded launchers. It does not change acceptance rules; the
  Skills view reports the 90/100 gates from recorded evaluations only.
- The preview is a file-based frame stream from the worker's own camera at the worker's step
  rate; a separate 30 fps 720p preview stream is not implemented.
- Skinned characters, library skills, objects and composition are the next stages of `docs/DIRECTION.md`.
