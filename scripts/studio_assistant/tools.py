"""Studio tools exposed to the assistant. Every tool is a plain function returning a JSON-serialisable
dict; `TOOL_SPECS` carries the schema each provider adapter translates into its own format.

The tools act only through the recorded launchers and the live worker's command file, exactly like
the control center, so every assistant action leaves the same evidence as a button press.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from studio_assistant import ARTIFACTS, CONFIG, ROOT, RUNTIME, SCRIPTS

LIVE_POINTER = RUNTIME / "studio-live-current.json"
CANCEL = threading.Event()   # set by the interface's Stop button; waiting tools return early


def cancelled() -> bool:
    return CANCEL.is_set()
GPU_LOCK = RUNTIME / "studio-gpu.lock"
SKILLS_DIR = ROOT / "skills"


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gpu_lock_held() -> bool:
    try:
        with open(GPU_LOCK, "a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def current_session() -> Optional[dict]:
    pointer = _read_json(LIVE_POINTER)
    if not pointer:
        return None
    finished = (Path(pointer["evidence"]) / "exit-code.txt").exists() or not _pid_alive(int(pointer.get("launcher_pid", 0) or 0))
    if finished:
        return None
    return pointer


def _state(session: dict) -> Optional[dict]:
    return _read_json(Path(session["output"]) / "live" / "state.json")


def _send(session: dict, command: dict, wait_s: float = 5.0) -> dict:
    """Append a command and wait for the worker's acknowledgement in status.jsonl."""
    output = Path(session["output"])
    status = output / "status.jsonl"
    before = sum(1 for _ in status.open()) if status.exists() else 0
    command = dict(command, issued_wall_time=time.time())
    with (output / "commands.jsonl").open("a") as stream:
        stream.write(json.dumps(command) + "\n")
    deadline = time.time() + wait_s
    while time.time() < deadline and not cancelled():
        if status.exists():
            lines = status.read_text().splitlines()
            for line in lines[before:]:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("event") == "command" and record.get("command", {}).get("cmd") == command["cmd"]:
                    return {"command": command["cmd"], "result": record.get("result"), "sim_time": record.get("sim_time"),
                            **{k: v for k, v in record.items() if k in ("world_xy", "hold_xy", "spawn_xy", "room_half_size")}}
        time.sleep(0.05)
    return {"command": command["cmd"], "result": "no_acknowledgement_within_timeout"}


def _require_session() -> dict:
    session = current_session()
    if session is None:
        raise RuntimeError("no live session is running; call start_session first")
    return session


# ---------------------------------------------------------------- tools
def describe_studio() -> dict:
    """What exists right now: live session, scenes, controllers, skills, GPU lock."""
    session = current_session()
    scenes = [{"name": p.stem, **{k: v for k, v in (_read_json(p, {}) or {}).items() if k in ("description", "spawn_xy", "room_half_size")}}
              for p in sorted((CONFIG / "scenes").glob("*.json"))]
    controllers = [{"name": "tracker", "description": "tracker-driven walker: Milestone 1 tracker following clip references; walks to a point and stands still; no training"}]
    for d in sorted((ARTIFACTS / "milestone3").glob("train-rlft-*")):
        results = next(iter((d / "results").glob("*")), None) if (d / "results").exists() else None
        if results and (results / "inference_last.ckpt").exists():
            controllers.append({"name": results.name, "path": str(results), "description": "learned walking adapter (fidgets after arrival)"})
    return {"live_session": None if session is None else {**{k: session[k] for k in ("output", "container", "started_utc")}, "state": _state(session)},
            "gpu_lock_held": _gpu_lock_held(), "scenes": scenes, "controllers": controllers, "skills": list_skills()["skills"],
            "destination_frames": {"spawn": "metres relative to the session spawn (scene origin); use this with scenes",
                                   "world": "terrain coordinates", "local": "x ahead of the character, y to its left"}}


def describe_scene(name: str) -> dict:
    """Objects and footprint of a scene in scene (spawn-relative) metres."""
    meta = _read_json(CONFIG / "scenes" / f"{name}.json")
    if not meta:
        raise RuntimeError(f"unknown scene {name}")
    items = [{"name": i["name"], "kind": i["kind"], "center": i["center"], "size": i["size"], "height": i.get("height"), "collision": i.get("collision")}
             for i in meta.get("items", [])]
    return {"name": meta.get("name", name), "description": meta.get("description"), "spawn_xy": meta.get("spawn_xy"),
            "room_half_size": meta.get("room_half_size"), "items": items, "route": meta.get("route"),
            "note": "destinations are not planned around obstacles; keep 0.6 m clear of collision items"}


def start_session(controller: str = "tracker", scene: Optional[str] = None, preview: str = "960x540", wait_s: float = 150.0) -> dict:
    """Start an interactive live session (one GPU job at a time). Returns once the worker publishes its first state."""
    if current_session() is not None:
        raise RuntimeError("a live session is already running; use it or call end_session first")
    if _gpu_lock_held():
        raise RuntimeError("another studio GPU job holds the lock")
    scenes = sorted(p.stem for p in (CONFIG / "scenes").glob("*.json"))
    if scene and scene not in scenes:
        raise RuntimeError(f"unknown scene {scene!r}; available scenes: {scenes}")
    target = controller
    if controller != "tracker":
        candidates = [c for c in describe_studio()["controllers"] if c["name"] == controller and "path" in c]
        if not candidates:
            raise RuntimeError(f"unknown controller {controller}")
        target = candidates[0]["path"]
    argv = [str(SCRIPTS / "run_milestone3_live.sh"), target, "--interactive", "--preview", preview, "--label", "assistant"]
    if scene:
        argv += ["--scene", scene]
    log = RUNTIME / "assistant-live-launch.log"
    before = (_read_json(LIVE_POINTER) or {}).get("started_utc")
    with log.open("a") as stream:
        stream.write(f"=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {' '.join(argv)}\n")
        stream.flush()
        process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + wait_s
    while time.time() < deadline and not cancelled():
        pointer = _read_json(LIVE_POINTER)
        if pointer and pointer.get("started_utc") != before:
            state = _read_json(Path(pointer["output"]) / "live" / "state.json")
            if state:
                return {"started": True, "session": pointer["output"], "controller": controller, "scene": scene, "state": state}
            if (Path(pointer["evidence"]) / "exit-code.txt").exists():
                raise RuntimeError(f"the launcher exited before the session started; see {pointer['evidence']}")
        if process.poll() is not None:
            tail = "".join(log.read_text(errors="replace").splitlines(keepends=True)[-6:]).strip()
            raise RuntimeError(f"the launcher exited with code {process.returncode} before starting a session: {tail[-600:]}")
        time.sleep(0.5)
    if cancelled():
        raise RuntimeError("cancelled by the user; the session may still be starting in the background")
    raise RuntimeError("the session did not publish a state within the wait time")


def end_session(wait_s: float = 120.0) -> dict:
    """Send quit; the worker finishes its recording and the launcher records the evidence."""
    session = _require_session()
    ack = _send(session, {"cmd": "quit"})
    deadline = time.time() + wait_s
    evidence = Path(session["evidence"])
    while time.time() < deadline and not (evidence / "exit-code.txt").exists() and not cancelled():
        time.sleep(0.5)
    outcome = _read_json(evidence / "outcome.json", {}) or {}
    return {"quit": ack, "evidence": str(evidence), "outcome": outcome.get("status"), "recording": str(Path(session["output"]) / "performance.mp4")}


def get_state() -> dict:
    """Latest published state of the character (position, speed, state, phase, destination)."""
    session = _require_session()
    state = _state(session)
    if state is None:
        raise RuntimeError("the worker has not published a state yet")
    return state


def walk_to(x: float, y: float, frame: str = "spawn") -> dict:
    """Send the character to a point. frame: spawn (scene metres), world, or local."""
    if frame not in ("spawn", "world", "local"):
        raise RuntimeError("frame must be spawn, world or local")
    return _send(_require_session(), {"cmd": "destination", "x": float(x), "y": float(y), "frame": frame})


def stop() -> dict:
    """Request a balanced stop where the character is."""
    return _send(_require_session(), {"cmd": "stop"})


def pause() -> dict:
    """Freeze simulated time until resume."""
    return _send(_require_session(), {"cmd": "pause"})


def resume() -> dict:
    """Continue simulated time after pause."""
    return _send(_require_session(), {"cmd": "resume"})


def reset() -> dict:
    """Explicitly return the character to the spawn point (required after a fall)."""
    return _send(_require_session(), {"cmd": "reset"})


def push(vx: float, vy: float) -> dict:
    """Apply a horizontal velocity impulse in m/s (a shove)."""
    return _send(_require_session(), {"cmd": "push", "vx": float(vx), "vy": float(vy)})


def record(action: str, name: str = "") -> dict:
    """Mark the start or stop of a named recording segment."""
    if action not in ("start", "stop"):
        raise RuntimeError("action must be start or stop")
    command = {"cmd": "record", "action": action}
    if name:
        command["name"] = name
    return _send(_require_session(), command)


def wait_until(condition: str, timeout_s: float = 20.0) -> dict:
    """Block until the character reaches a condition: arrived (within 0.3 m of its destination), standing, fallen, or stopped."""
    session = _require_session()
    deadline = time.time() + max(0.0, min(float(timeout_s), 120.0))
    last = None
    while time.time() < deadline and not cancelled():
        state = _state(session)
        if state:
            last = state
            if condition == "arrived" and state.get("destination") and state.get("distance", 9) < 0.3:
                return {"met": True, "state": state}
            if condition == "standing" and state.get("state") == "standing":
                return {"met": True, "state": state}
            if condition == "fallen" and state.get("fallen"):
                return {"met": True, "state": state}
            if condition == "stopped" and state.get("speed", 1) < 0.15 and state.get("state") in ("standing", "stopping"):
                return {"met": True, "state": state}
        time.sleep(0.1)
    return {"met": False, "cancelled": cancelled(), "state": last}


def list_skills() -> dict:
    """Skills available to play. Locomotion is built in; library skills come from skills/<name>/skill.json."""
    skills = [{"name": "walk_to", "kind": "builtin", "description": "walk to a point and stand (tracker-driven walker)"},
              {"name": "stand", "kind": "builtin", "description": "stop and stand still"}]
    for meta in sorted(SKILLS_DIR.glob("*/skill.json")):
        data = _read_json(meta, {}) or {}
        skills.append({"name": meta.parent.name, "kind": "library", "description": data.get("description"), "tags": data.get("tags"),
                       "duration_s": data.get("duration_s"), "licence": data.get("licence", {}).get("name") if isinstance(data.get("licence"), dict) else data.get("licence")})
    return {"skills": skills}


def play_skill(name: str, **parameters) -> dict:
    """Play a library skill in the live session (library playback arrives with the skill library stage)."""
    if name == "walk_to":
        return walk_to(parameters.get("x", 0.0), parameters.get("y", 0.0), parameters.get("frame", "spawn"))
    if name == "stand":
        return stop()
    if (SKILLS_DIR / name / "skill.json").exists():
        raise RuntimeError(f"skill {name} exists in the library but playback of library skills is not implemented yet")
    raise RuntimeError(f"unknown skill {name}; call list_skills")


TOOLS: dict[str, Callable] = {f.__name__: f for f in (
    describe_studio, describe_scene, start_session, end_session, get_state, walk_to, stop, pause, resume, reset, push, record,
    wait_until, list_skills, play_skill)}

TOOL_SPECS = [
    {"name": "describe_studio", "description": "Current live session, available scenes, controllers, skills and GPU lock. Call first.", "parameters": {"type": "object", "properties": {}}},
    {"name": "describe_scene", "description": "Objects, sizes and positions of a scene in scene metres (origin = spawn).",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "start_session", "description": "Start an interactive live session with a controller (tracker = tracker-driven walker, or an adapter name) and optional scene. Takes about a minute.",
     "parameters": {"type": "object", "properties": {"controller": {"type": "string", "default": "tracker"}, "scene": {"type": "string"}, "preview": {"type": "string", "default": "960x540"}}}},
    {"name": "end_session", "description": "End the live session cleanly (records the evidence).", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_state", "description": "Latest character state: position, speed, state, phase, destination, distance.", "parameters": {"type": "object", "properties": {}}},
    {"name": "walk_to", "description": "Send the character to a point. frame spawn = scene metres from the spawn, world = terrain metres, local = x ahead / y left of the character.",
     "parameters": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "frame": {"type": "string", "enum": ["spawn", "world", "local"], "default": "spawn"}}, "required": ["x", "y"]}},
    {"name": "stop", "description": "Stop walking and stand where the character is.", "parameters": {"type": "object", "properties": {}}},
    {"name": "pause", "description": "Freeze simulated time.", "parameters": {"type": "object", "properties": {}}},
    {"name": "resume", "description": "Continue after pause.", "parameters": {"type": "object", "properties": {}}},
    {"name": "reset", "description": "Return the character to the spawn point; required after a fall.", "parameters": {"type": "object", "properties": {}}},
    {"name": "push", "description": "Shove the character with a horizontal velocity impulse in m/s.",
     "parameters": {"type": "object", "properties": {"vx": {"type": "number"}, "vy": {"type": "number"}}, "required": ["vx", "vy"]}},
    {"name": "record", "description": "Start or stop a named recording segment.",
     "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["start", "stop"]}, "name": {"type": "string"}}, "required": ["action"]}},
    {"name": "wait_until", "description": "Wait until the character has arrived, is standing, has fallen, or has stopped (max 120 s).",
     "parameters": {"type": "object", "properties": {"condition": {"type": "string", "enum": ["arrived", "standing", "fallen", "stopped"]}, "timeout_s": {"type": "number", "default": 20}}, "required": ["condition"]}},
    {"name": "list_skills", "description": "Skills that can be played.", "parameters": {"type": "object", "properties": {}}},
    {"name": "play_skill", "description": "Play a skill by name with parameters (x, y, frame for walk_to).",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "frame": {"type": "string"}}, "required": ["name"]}},
]


def call_tool(name: str, arguments: dict) -> dict:
    """Run a tool by name; errors come back as data so the model can react."""
    function = TOOLS.get(name)
    if function is None:
        return {"error": f"unknown tool {name}"}
    try:
        return function(**(arguments or {}))
    except Exception as error:  # the model should see failures, not crash the assistant
        return {"error": str(error)}


SYSTEM_PROMPT = """You are the director's assistant of the Digital Human Studio: a local desktop studio where a
physically simulated human character acts in a scene. You direct the character through tools that do
exactly what the control center's buttons do. Rules:
- Call describe_studio first in a conversation to learn what is running and what exists.
- Positions in scenes are in metres relative to the spawn (frame "spawn"); describe_scene gives object
  positions in that frame. Keep destinations at least 0.6 m clear of collision objects; there is no
  obstacle avoidance, so route around things with intermediate walk_to calls when needed.
- After walk_to, use wait_until("arrived") then wait_until("standing") before the next step if the user
  asked for a sequence. After a fall, call reset before anything else.
- Only one GPU job runs at a time; starting a session takes about a minute. Do not end a session the
  user did not ask to end.
- Be brief in replies: say what you did and what the character is doing now. Report failures plainly.
"""
