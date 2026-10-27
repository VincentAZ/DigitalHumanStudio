# Digital Human Studio: what the app does today (brief for the UI redesign)

> Status 2026-10-27: the redesign delivered against this brief (`Astra Redesign/`) was implemented as
> `scripts/studio_app/web/` and wired to the back end described below; see `docs/CONTROL_CENTER.md`.

Audience: whoever designs the new interface. This describes only the parts in use. Training,
evaluation and the comparison tools are retired and must not appear. The redesign replaces the
current PySide6 window (`scripts/studio_app/`); the back end stays as is and is described at the
end so the new UI can be wired to it.

## The product in one sentence

A local desktop studio where a physically simulated human character acts in a scene, directed either
by hand (click where it should go, press stop, reset, push) or by telling an AI assistant what to do,
with everything recorded.

## Who uses it and how

One person at a desk with a big screen and a strong GPU. A session is: pick a scene, pick how the
character moves (today: the "tracker-driven walker"), start, then direct the character for minutes to
an hour, watching it in the preview, and end the session. Over time the person builds a library of
skills (behaviours) the character can perform; the assistant will generate and compose them.

## Screens and what each must do

### 1. Live scene (the main screen; most of the time is spent here)

- **Session bar**: choose the controller (list; default "Tracker-driven walker"), choose the scene
  (list; "Flat floor" or a named scene such as "workcell"), choose the preview size (640x480,
  960x540, 1280x720), start the session, end the session (clean), force stop (emergency). A status
  line shows the session name, what is running, and the preview size.
- **Preview**: the rendered camera view of the character, updated about 15 to 18 times per second.
  Dark background when no session. This is the largest element.
- **Room map**: top-down map of the room around the spawn point, with a grid in metres, the scene's
  objects drawn as footprints (walls, machine, conveyor, rack, pallets, posts, floor markings), the
  character as a heading arrow coloured by state, its trail, and the destination as a circle.
  **Clicking anywhere sends the character there.** A legend shows state colours: walking, standing,
  stopping, fallen, paused.
- **Controls**: Stop walking · Pause/Resume (one toggle) · Reset (explicit return to the spawn;
  required after a fall) · Start/stop recording segment · Walk relative (x metres ahead, y metres
  left, button) · Push (vx, vy in m/s, button).
- **Character status**: state (with "fallen: reset required" when fallen, and the reference phase
  such as walk/stop/idle), simulated time and step, pelvis speed, distance to target, control steps
  per wall second, resets, recording state.
- **Command acknowledgements**: a scrolling log of every command sent and its result (accepted,
  rejected out of bounds, rejected because fallen, latency).
- **Behaviour rules the UI must respect**: one session at a time (the GPU is shared); starting takes
  about a minute, so show progress; while fallen, destinations are rejected until Reset; a session
  that was ended cleanly leaves a recording and evidence folder; force stop records a failed session.

### 2. Assistant (always visible beside the live scene)

- Provider picker: Claude (Agent SDK, needs an Anthropic API key), OpenAI, Google Gemini, xAI Grok,
  OpenRouter, LM Studio (local, no key). A status line: key set / no key, model, thinking level.
- Settings dialog per provider: API key (hidden, with show), model (editable list with "Fetch
  models" from the provider), thinking level (default/low/medium/high/xhigh/max), base URL for
  OpenAI-compatible providers, "Forget stored key". Keys live in a per-user file, never in the project.
- Conversation view: user messages, streamed assistant text, and the tool calls the assistant makes
  shown inline with their results (e.g. `walk_to({x: 2.5, y: 0.3, frame: "spawn"})` → accepted).
- Input box with Send (Ctrl+Enter) and Stop. "New conversation" resets. While the assistant works it may wait on the
  simulation (a session start takes a minute, "wait until standing" up to two); the person must be able to
  interrupt (Stop) and to keep using the hand controls meanwhile. Observed need: a user asked "how can I just reply
  when I want?" while the assistant was waiting.
- Typical sentences: "load the work cell and walk to the machine", "stop", "push her from the left",
  "walk to the conveyor, wait until she is standing, then come back".

### 3. Skills

- The skill library. Today it lists the locomotion controllers (the tracker-driven walker, and the
  retired trained adapters kept for comparison). Next stages add library skills: each with a name,
  description, tags, duration, licence, a preview thumbnail/video, and "play in the live scene".
  Design it as a browsable library (grid or list with previews, search, tags), not a table of
  training runs.

### 4. Project

- Facts: workspace path, locked runtime image digest, interface Python and Qt versions, GPU name
  and load, running containers, GPU lock state, milestone records.
- Buttons: launch Mixar (character tool), open the plan, open the progress log, open the
  diagnostics folder. Latest progress-log headings.

### 5. Job output (bottom strip)

- The text output of launchers started from the window (session start/end). Can be a collapsible
  drawer. The status bar shows GPU load and memory, the GPU lock, running containers, and the
  active jobs.

## Things that must be visible at all times

GPU busy or free; whether a session is running and which scene; whether the character has fallen.

## Not in the product now (do not design for)

Training, evaluation, comparison runs, reward plots, checkpoints, seeds, batch sizes.

## Back end the new UI talks to (unchanged)

- A live session is started by running `scripts/run_milestone3_live.sh <controller> --interactive
  [--scene name] [--preview WxH]`. While it runs, the file `.runtime/studio-live-current.json`
  names the session's output folder.
- In that folder: `live/frame.jpg` (latest preview frame, replaced atomically), `live/state.json`
  (character state: position, heading, speed, state, phase, destination, distance, spawn, room size,
  fallen, paused, recording, steps per second), `status.jsonl` (acknowledgements), `commands.jsonl`
  (append one JSON line per command: `{"cmd":"destination","x":..,"y":..,"frame":"spawn|world|local"}`,
  `{"cmd":"stop"}`, `{"cmd":"pause"}`, `{"cmd":"resume"}`, `{"cmd":"reset"}`, `{"cmd":"push","vx":..,"vy":..}`,
  `{"cmd":"record","action":"start|stop","name":".."}`, `{"cmd":"quit"}`), `scene.json` (footprints to draw).
- Scenes: `config/scenes/<name>.json` (name, description, spawn, room size, items with centre/size/
  colour/collision) and `<name>.usda`.
- Assistant: the Python package `scripts/studio_assistant/` (providers, settings file, tools).
  The UI only needs to call `make_assistant(provider).run_turn(text, on_event)` and render events:
  text deltas, tool_call, tool_result, error, done.
- The current Qt implementation of all of the above is in `scripts/studio_app/` and can be read as
  the behavioural reference: `live.py` (session, map, controls), `assistant.py`, `skills.py`,
  `project.py`, `state.py` (how files are read), `jobs.py` (how launchers are started).
