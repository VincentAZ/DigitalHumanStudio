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
| Live scene | Pick the scene, the controller (default: the tracker-driven walker), the mode (physical: the tracker acts and physics decides; kinematic playback: the composed reference is played exactly, no falls), the character (the capsule mannequin or a prepared skinned rig) and the preview size, start an interactive Isaac worker (a progress overlay covers the minute it takes), watch the camera frame, click the top-down room map to send the character somewhere or click an object on it to walk to the object's approach point, walk relative to the character, stop (walking, the playing skill and any running sequence), pause/resume simulated time, reset explicitly (required after a fall, which shows a banner), push the character, mark recording segments, end the session cleanly or force stop. The viewport shows the skill being played (with its frame progress) and the running sequence's step; telemetry (state and reference phase, simulated time, pelvis speed, distance to the destination, control rate, resets) and the command activity log update live. |
| Skill library | The shipped library: 61 licensed BONES-SEED motion-capture clips (dance, gestures, locomotion, idle, actions, floor work) with stick-figure thumbnails and animated previews, plus generated clips and saved sequences. Search, filter by category, open a skill's details (measured duration, entry and exit pose, travel, source, licence, provenance), play it in the running session (also at half speed or twice), or add it to the sequence composer. The composer chains walk-to steps (to an object or back to the spawn), clips with an optional "take this object at frame N / put it down" grasp, and waits; run it in the scene or save it as a composite skill. "Create a skill" generates a new clip from a text description with the local text-to-motion model when it is installed (`docs/MOTION_GENERATION.md`). |
| Characters | Skinned characters prepared from licence-checked downloads (`config/character-sources.json`, `scripts/fetch_characters.py`): name, licence, source, vertex and joint counts, how many of the 23 bodies the rig maps. "Use next" selects the character for the next session. |
| Project | Locked image digest, interface versions, milestone records, workspace path, live GPU load and memory, the studio lock and running containers, shortcuts (Mixar, the direction document, the progress log, the diagnostics folder) and the latest progress-log entries. |

The assistant panel stays beside every view. The status bar shows whether the GPU is busy, its load
and memory, the running containers, the session state and a button that opens the job-output drawer
(the output of launchers started from the window; the full text is also appended to
`.runtime/studio-app.log`). The sidebar shows the current session at all times.

## Interactive tutorial

`Interactive tutorial` in the sidebar starts a guided tour of 36 numbered steps (`scripts/studio_app/web/tour.js`).
Each step dims the window, spotlights one control and explains it; a step that asks for an action
(start a session, click the map, pause, record, push, play a clip, run a sequence, end the session)
advances by itself when the studio reports the result, and offers "Do it for me". The tour can be
hidden or skipped at any time and resumes from the sidebar at the step it was left on (progress is
kept in the page's local storage); it opens on the first launch and restarts from the beginning once
completed. Keyboard: → next, ← back, Esc hide. The whole tour takes about fifteen minutes and starts
a real session, so it needs the GPU free.

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

## Skills, sequences and objects

A skill is a folder under `skills/` (format in `skills/README.md`). The worker is started with the
library mounted read-only; `play_skill` builds a segment from the clip's frames, aligned to the
character's current heading, and the same reference composer that drives walking plays it: in a
physical session the Milestone 1 tracker follows the clip (acrobatic or floor clips can make it fall,
which is reported like any fall), in a kinematic session the reference is written into the simulator
every step. `sequence` runs an ordered list of steps inside the worker, waiting for each to finish:
`walk_to` (a point or an object's approach point), a clip (with `attach`/`release` of an object at a
clip frame), `attach`, `release`, `place_object`, `wait` and `stand`. Scene objects (`objects` in the
scene's JSON, visual prims without collision in the USD) follow the chosen hand while attached and
are put down on whatever surface is under the hand when released. `status.jsonl` records
`skill_finished`, `sequence_step_done`, `sequence_finished`, `attached` and `released` events;
`summary.json` lists the skills played and the sequences run.

## Skinned characters

`scripts/fetch_characters.py` verifies the downloaded rigs against `config/character-sources.json`
(hashes and licences), copies each licence text and prepares `.runtime/characters/<id>/` with
`scripts/prepare_character.py` on the CPU inside the pinned image: `rig.npz` (joints, bind
transforms, meshes with skin weights and uvs), the textures and `character.json`. The worker loads
that folder (`--character`), aligns the rig's bind pose to the physics body's rest pose (every mapped
joint is rotated so its bone follows the matching body's bone; fingers, eyes and other unmapped joints
ride on their nearest mapped ancestor; rigs without a shoulder or second spine joint skip those
bodies), hides the capsule body and, after every control step, skins the mesh on the GPU from the 23
body transforms and writes the points and normals into USD mesh prims. The first characters are the
SOMA-X neutral body (NVIDIA, Apache-2.0: the skeleton the physics body derives from, so the map is the
identity), the Quaternius Superhero bodies (CC0, textured) and Cesium Man (CC-BY 4.0); see
`docs/CHARACTERS.md` for the survey and the mapping tables.

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
- plays library clips and sequences, moves attached objects and, with `--character`, renders the
  skinned character (see above); in `--mode kinematic` it writes the composed reference into the
  simulator instead of running the tracker, measures the pelvis speed from the written poses and
  reports no falls;
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
resume, reset, push, mark recordings, wait for arrival, standing, a finished skill or sequence, list,
search and inspect skills, play a skill, run and save sequences, attach, release and place objects,
generate a skill from text, list characters) over the recorded launchers and the live command file,
so every assistant action leaves the same evidence as a button press. Providers: Claude through the Claude Agent SDK (needs an Anthropic API key; Anthropic
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
footprint (`workcell.json`: the same boxes in scene-relative metres with their top heights, the pinned
spawn on the flat terrain, the room size, the comparison route, and the graspable props: a cup on the
conveyor and a carton on a pallet, each with an approach point and the hand that takes it). The Live scene's Scene picker passes the scene to
the launcher, which references it into the stage at the spawn before the simulation plays, pins the
spawn there, and copies the footprint into the session so the room map and the recorded top-down plot
draw it. Destinations are not planned around obstacles: a click inside the machine sends the character
into the machine. Add a scene by extending the builder or dropping a `<name>.usda` plus `<name>.json`
pair into `config/scenes/`.

## Limits

- The interface is a view over recorded launchers. It does not change acceptance rules.
- The preview is a file-based frame stream from the worker's own camera at the worker's step
  rate; a separate 30 fps 720p preview stream is not implemented.
- Grasps are kinematic: an attached object snaps to the hand at the chosen frame; there is no
  contact-based grasping, and clips were captured without the studio's props, so hands pass near,
  not exactly onto, objects.
- Retargeted rigs keep their own proportions, so hands and feet of a rig with other limb lengths do
  not land exactly where the physics body's do.
- Physical playback of floor and acrobatic clips can end in a fall; kinematic playback cannot fall
  but ignores contact.
