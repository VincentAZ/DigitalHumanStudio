# Control center

`scripts/studio.sh` launches the Digital Human Studio control center: one desktop window from
which you direct the character, by hand or through the assistant, in a scene. Since 2026-10-27 the
interface is the Astra redesign: an HTML/CSS/JS page (`scripts/studio_app/web/`) hosted in Qt
WebEngine inside a PySide6 window, wired to the back end through `scripts/studio_app/bridge.py`. It is built on top of the recorded live-session launcher rather than replacing it: every
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
| Live scene | Pick the scene, the controller (default: the tracker-driven walker) and the preview size, start an interactive Isaac worker (a progress overlay covers the minute it takes), watch the camera frame, click the top-down room map to send the character somewhere, walk relative to the character, stop walking, pause/resume simulated time, reset explicitly (required after a fall, which shows a banner), push the character, mark recording segments, end the session cleanly or force stop. Telemetry (state and reference phase, simulated time, pelvis speed, distance to the destination, control rate, resets) and the command activity log update live. |
| Skill library | A browsable library with search and category filters. Today it holds the tracker-driven walker; shipped clips, generated motions and composed skills arrive with the next stages of `docs/DIRECTION.md`. "Create a skill" hands a motion description to the assistant. |
| Project | Locked image digest, interface versions, milestone records, workspace path, live GPU load and memory, the studio lock and running containers, shortcuts (Mixar, the direction document, the progress log, the diagnostics folder) and the latest progress-log entries. |

The assistant panel stays beside every view. The status bar shows whether the GPU is busy, its load
and memory, the running containers, the session state and a button that opens the job-output drawer
(the output of launchers started from the window; the full text is also appended to
`.runtime/studio-app.log`). The sidebar shows the current session at all times.

## How the interface is wired

`scripts/studio_app/main.py` opens one `QWebEngineView` on `scripts/studio_app/web/index.html` and
registers `Bridge` (`scripts/studio_app/bridge.py`) on a Qt WebChannel. The page calls the bridge's
slots (start/end a session, append a command, provider settings, assistant turns, open a folder) and
polls `poll(cursor, state_token)` about fifteen times a second, which returns the latest
`live/state.json`, the frame URL (`live/frame.jpg` with its modification time as cache buster) and
every event that happened since the cursor: command acknowledgements from `status.jsonl`, session
phase changes, host status, launcher output and streamed assistant events. Qt-to-page signals are
deliberately not used; their delivery was lost after page reloads. `STUDIO_DEVTOOLS=<port>`
exposes Chromium's remote debugging on localhost for the interface only. The retired Qt Widgets
interface lives in `sandbox/qt-widgets-ui/`, the design study it replaced in `Astra Redesign/`.

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

The right-hand panel is a chat with an AI assistant that drives the studio through the same
operations as the buttons: `scripts/studio_assistant/tools.py` defines the tools (describe the studio
and a scene, start or end a live session, walk to a point in scene/world/local frames, stop, pause,
resume, reset, push, mark recordings, wait for arrival or standing, list and play skills) over the
recorded launchers and the live command file, so every assistant action leaves the same evidence as a
button press. Providers: Claude through the Claude Agent SDK (needs an Anthropic API key; Anthropic
does not allow third-party apps to use the claude.ai sign-in), and OpenAI, Google Gemini, xAI Grok and
OpenRouter through one OpenAI-compatible adapter, and LM Studio (a local server, no key). Keys come from the environment (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`) or from
`~/.config/digital-human-studio/providers.json` (written by the provider settings dialog with mode 600,
together with the model, the thinking level and the base URL); the
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

- The interface is a view over recorded launchers. It does not change acceptance rules.
- Without a destination the walker's idle creeps slowly (a few centimetres per second); give it a
  destination or a stop to hold a spot.
- The preview is a file-based frame stream from the worker's own camera at the worker's step
  rate; a separate 30 fps 720p preview stream is not implemented.
- Skinned characters, library skills, objects and composition are the next stages of `docs/DIRECTION.md`.
