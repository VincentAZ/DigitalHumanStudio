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
                if record.get("event") == "command" and record.get("command", {}).get("cmd") == command["cmd"] \
                        and record["command"].get("issued_wall_time") == command["issued_wall_time"]:
                    return {"command": command["cmd"], "result": record.get("result"), "sim_time": record.get("sim_time"),
                            **{k: v for k, v in record.items() if k in ("world_xy", "hold_xy", "spawn_xy", "room_half_size", "reason", "frames",
                                                                         "duration_s", "entry_pose", "exit_pose", "steps", "name", "position")},
                            "_line": before + lines.index(line) + 1}
        time.sleep(0.05)
    return {"command": command["cmd"], "result": "no_acknowledgement_within_timeout"}


def _wait_event(session: dict, after_line: int, events: tuple, timeout_s: float) -> Optional[dict]:
    """The first status record of one of ``events`` written after status line ``after_line``."""
    status = Path(session["output"]) / "status.jsonl"
    deadline = time.time() + max(0.0, min(float(timeout_s), 600.0))
    while time.time() < deadline and not cancelled():
        if status.exists():
            lines = status.read_text().splitlines()
            for line in lines[after_line:]:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("event") in events:
                    return record
        time.sleep(0.1)
    return None


def _public(ack: dict) -> dict:
    return {k: v for k, v in ack.items() if not k.startswith("_")}


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
    skills = list_skills()["skills"]
    return {"live_session": None if session is None else {**{k: session.get(k) for k in ("output", "container", "started_utc", "mode", "scene", "character")},
                                                            "state": _state(session)},
            "gpu_lock_held": _gpu_lock_held(), "scenes": scenes, "controllers": controllers,
            "modes": {"physical": "the tracker acts and physics decides (falls are possible)", "kinematic": "the composed reference is played back exactly (no falls, no contact)"},
            "skills_summary": {"count": len(skills), "categories": sorted({s.get("category", "") for s in skills}),
                               "note": "call search_skills or list_skills for details; play_skill plays one in the live session"},
            "characters": list_characters()["characters"],
            "destination_frames": {"spawn": "metres relative to the session spawn (scene origin); use this with scenes",
                                   "world": "terrain coordinates", "local": "x ahead of the character, y to its left"}}


def describe_scene(name: str) -> dict:
    """Objects and footprint of a scene in scene (spawn-relative) metres."""
    meta = _read_json(CONFIG / "scenes" / f"{name}.json")
    if not meta:
        raise RuntimeError(f"unknown scene {name}")
    items = [{"name": i["name"], "kind": i["kind"], "center": i["center"], "size": i["size"], "height": i.get("height"), "collision": i.get("collision")}
             for i in meta.get("items", [])]
    objects = [{"name": o["name"], "description": o.get("description"), "position": o.get("center"), "approach": o.get("approach"),
                "hand": o.get("hand", "RightHand"), "graspable": o.get("graspable", False)} for o in meta.get("objects", [])]
    return {"name": meta.get("name", name), "description": meta.get("description"), "spawn_xy": meta.get("spawn_xy"),
            "room_half_size": meta.get("room_half_size"), "items": items, "objects": objects, "route": meta.get("route"),
            "note": "destinations are not planned around obstacles; keep 0.6 m clear of collision items; walk_to(object=name) goes to an object's approach point"}


def start_session(controller: str = "tracker", scene: Optional[str] = None, preview: str = "960x540", mode: str = "physical",
                  character: str = "", wait_s: float = 150.0) -> dict:
    """Start an interactive live session (one GPU job at a time). Returns once the worker publishes its first state."""
    if mode not in ("physical", "kinematic"):
        raise RuntimeError("mode must be physical or kinematic")
    if character and not (RUNTIME / "characters" / character / "character.json").exists():
        raise RuntimeError(f"unknown character {character!r}; call describe_studio for the list")
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
    argv = [str(SCRIPTS / "run_milestone3_live.sh"), target, "--interactive", "--preview", preview, "--label", "assistant", "--mode", mode]
    if scene:
        argv += ["--scene", scene]
    if character:
        argv += ["--character", character]
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
                return {"started": True, "session": pointer["output"], "controller": controller, "scene": scene, "mode": mode, "character": character, "state": state}
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


def walk_to(x: float = 0.0, y: float = 0.0, frame: str = "spawn", object: str = "") -> dict:
    """Send the character to a point (frame: spawn, world, local) or to an object's approach point."""
    if frame not in ("spawn", "world", "local"):
        raise RuntimeError("frame must be spawn, world or local")
    command = {"cmd": "destination", "x": float(x), "y": float(y), "frame": frame}
    if object:
        command["object"] = object
    return _public(_send(_require_session(), command))


def stop() -> dict:
    """Request a balanced stop where the character is."""
    return _public(_send(_require_session(), {"cmd": "stop"}))


def pause() -> dict:
    """Freeze simulated time until resume."""
    return _public(_send(_require_session(), {"cmd": "pause"}))


def resume() -> dict:
    """Continue simulated time after pause."""
    return _public(_send(_require_session(), {"cmd": "resume"}))


def reset() -> dict:
    """Explicitly return the character to the spawn point (required after a fall)."""
    return _public(_send(_require_session(), {"cmd": "reset"}))


def push(vx: float, vy: float) -> dict:
    """Apply a horizontal velocity impulse in m/s (a shove)."""
    return _public(_send(_require_session(), {"cmd": "push", "vx": float(vx), "vy": float(vy)}))


def record(action: str, name: str = "") -> dict:
    """Mark the start or stop of a named recording segment."""
    if action not in ("start", "stop"):
        raise RuntimeError("action must be start or stop")
    command = {"cmd": "record", "action": action}
    if name:
        command["name"] = name
    return _public(_send(_require_session(), command))


def wait_until(condition: str, timeout_s: float = 20.0) -> dict:
    """Block until the character reaches a condition: arrived (within 0.3 m of its destination), standing, fallen, stopped,
    skill_done (no skill playing) or sequence_done (no sequence running)."""
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
            if condition == "skill_done" and not state.get("skill"):
                return {"met": True, "state": state}
            if condition == "sequence_done" and not state.get("sequence"):
                return {"met": True, "state": state}
        time.sleep(0.1)
    return {"met": False, "cancelled": cancelled(), "state": last}


def _skill_records() -> list[dict]:
    from studio_walk.skill_lib import list_skills as _list
    return _list(SKILLS_DIR)


def _skill_summary(meta: dict) -> dict:
    licence = meta.get("licence")
    return {"name": meta["id"], "title": meta.get("name"), "kind": meta.get("kind", "clip"), "category": meta.get("category"),
            "description": meta.get("description"), "tags": meta.get("tags", []), "duration_s": meta.get("duration_s"),
            "entry_pose": meta.get("entry_pose"), "exit_pose": meta.get("exit_pose"), "loop": meta.get("loop", False),
            "travel_m": meta.get("travel_m"), "licence": licence.get("name") if isinstance(licence, dict) else licence,
            **({"steps": meta.get("steps")} if meta.get("kind") == "sequence" else {})}


def list_skills() -> dict:
    """Skills available to play: the built-in walker plus every library skill (clips, generated clips, sequences)."""
    skills = [{"name": "walk_to", "kind": "builtin", "category": "locomotion", "description": "walk to a point or an object's approach point and stand (tracker-driven walker)"},
              {"name": "stand", "kind": "builtin", "category": "locomotion", "description": "stop and stand still"}]
    skills += [_skill_summary(meta) for meta in _skill_records()]
    return {"skills": skills, "count": len(skills)}


def search_skills(query: str = "", category: str = "", limit: int = 12) -> dict:
    """Find library skills by words in their name, description or tags (optionally within a category)."""
    words = [w for w in query.lower().replace("_", " ").split() if w]
    scored = []
    for meta in _skill_records():
        if category and meta.get("category") != category:
            continue
        haystack = " ".join([meta["id"], meta.get("name", ""), meta.get("description", ""), " ".join(meta.get("tags", []))]).lower().replace("_", " ")
        score = sum(2 if w in meta.get("name", "").lower() else 1 for w in words if w in haystack)
        if words and score == 0:
            continue
        scored.append((score, meta))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return {"query": query, "category": category, "skills": [_skill_summary(m) for _, m in scored[:max(1, min(int(limit), 40))]],
            "categories": sorted({m.get("category", "") for m in _skill_records()})}


def get_skill(name: str) -> dict:
    """Full metadata of one library skill (source, licence, provenance, measured motion, steps of a sequence)."""
    from studio_walk.skill_lib import read_skill
    meta = read_skill(SKILLS_DIR / name)
    if meta is None:
        raise RuntimeError(f"unknown skill {name}; call search_skills")
    return meta


def play_skill(name: str, loops: int = 1, speed: float = 1.0, wait: bool = False, **parameters) -> dict:
    """Play a skill in the live session: a library clip (through the tracker, or exactly in kinematic mode), a saved sequence,
    or the built-ins walk_to / stand. wait=true blocks until the clip (or sequence) has finished, up to 10 minutes."""
    if name == "walk_to":
        return walk_to(parameters.get("x", 0.0), parameters.get("y", 0.0), parameters.get("frame", "spawn"), parameters.get("object", ""))
    if name == "stand":
        return stop()
    from studio_walk.skill_lib import read_skill
    meta = read_skill(SKILLS_DIR / name)
    if meta is None:
        raise RuntimeError(f"unknown skill {name}; call search_skills")
    if meta.get("kind") == "sequence":
        return run_sequence(meta.get("steps", []), name=meta["id"], wait=wait)
    session = _require_session()
    ack = _send(session, {"cmd": "play_skill", "skill": meta["id"], "loops": max(1, int(loops)), "speed": float(speed)})
    result = {**_public(ack), "skill": meta["id"], "title": meta.get("name"), "entry_pose": meta.get("entry_pose"), "exit_pose": meta.get("exit_pose")}
    if wait and ack.get("result") == "accepted":
        finished = _wait_event(session, ack["_line"], ("skill_finished", "fall_detected"), timeout_s=float(ack.get("duration_s", 10)) + 30)
        result["finished"] = finished is not None and finished.get("event") == "skill_finished" and not finished.get("interrupted")
        result["final_state"] = _state(session)
        if finished and finished.get("event") == "fall_detected":
            result["fell"] = True
    return result


def run_sequence(steps: list, name: str = "", wait: bool = False) -> dict:
    """Run a sequence in the live session. Steps: {"skill": "walk_to", "x","y","frame"} or {"skill":"walk_to","object":name};
    {"skill": "<clip id>", "loops", "speed", "attach": {"object","body","at_frame"}, "release": {"object","at_frame"}};
    {"skill": "attach"|"release"|"place_object", ...}; {"skill": "wait", "seconds"}; {"skill": "stand"}."""
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("steps must be a non-empty list")
    session = _require_session()
    ack = _send(session, {"cmd": "sequence", "name": name or "", "steps": steps})
    result = _public(ack)
    if wait and ack.get("result") == "accepted":
        finished = _wait_event(session, ack["_line"], ("sequence_finished",), timeout_s=600)
        result["finished"] = finished is not None and finished.get("status") == "finished"
        result["sequence_status"] = finished.get("status") if finished else "timeout"
        result["reason"] = finished.get("reason") if finished else None
        result["final_state"] = _state(session)
    return result


def save_sequence(name: str, description: str, steps: list, tags: Optional[list] = None) -> dict:
    """Save a sequence as a composite skill in the library (skills/<name>/skill.json). Names: lowercase letters, digits, underscores."""
    import re
    import datetime as dt
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,47}", name or ""):
        raise RuntimeError("name must be 3-48 characters: lowercase letters, digits and underscores, starting with a letter")
    if not isinstance(steps, list) or not steps or not all(isinstance(s, dict) and s.get("skill") for s in steps):
        raise RuntimeError("steps must be a non-empty list of objects with a skill")
    from studio_walk.skill_lib import read_skill
    for step in steps:
        if step["skill"] not in ("walk_to", "stand", "wait", "attach", "release", "place_object"):
            meta = read_skill(SKILLS_DIR / step["skill"])
            if meta is None or meta.get("kind") != "clip":
                raise RuntimeError(f"step skill {step['skill']} is not a clip in the library")
    folder = SKILLS_DIR / name
    existing = read_skill(folder)
    if existing is not None and existing.get("kind") != "sequence":
        raise RuntimeError(f"{name} already exists and is not a sequence")
    folder.mkdir(parents=True, exist_ok=True)
    duration = 0.0
    for step in steps:
        if step["skill"] == "wait":
            duration += float(step.get("seconds", 1.0))
        elif step["skill"] not in ("walk_to", "stand", "attach", "release", "place_object"):
            duration += float((read_skill(SKILLS_DIR / step["skill"]) or {}).get("duration_s", 0.0)) * int(step.get("loops", 1))
    meta = {"id": name, "kind": "sequence", "name": name.replace("_", " ").capitalize(), "description": description, "category": "sequence",
            "tags": sorted(set((tags or []) + ["sequence", "composed"])), "steps": steps, "duration_s": round(duration, 2),
            "entry_pose": "standing", "exit_pose": "standing", "licence": {"name": "composed from library skills; each step carries its own licence"},
            "provenance": {"created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "created_by": "assistant save_sequence"}}
    (folder / "skill.json").write_text(json.dumps(meta, indent=1) + "\n")
    return {"saved": True, "skill": name, "path": str(folder / "skill.json"), "steps": len(steps)}


def attach_object(object: str, body: str = "RightHand") -> dict:
    """Make a scene object follow a hand (RightHand or LeftHand) from now on."""
    return _public(_send(_require_session(), {"cmd": "attach", "object": object, "body": body}))


def release_object(object: str) -> dict:
    """Stop an object following the hand; it stays where it is."""
    return _public(_send(_require_session(), {"cmd": "release", "object": object}))


def place_object(object: str, x: float, y: float, z: float) -> dict:
    """Put a scene object at a point in scene metres (origin = spawn, z up)."""
    return _public(_send(_require_session(), {"cmd": "place_object", "object": object, "x": float(x), "y": float(y), "z": float(z)}))


def generate_skill(description: str, seconds: float = 4.0, name: str = "", seed: int = 0) -> dict:
    """Generate a new motion clip from a text description with the local text-to-motion model (Kimodo, SOMA skeleton),
    import it as a library skill and return it. Takes one to three minutes; the GPU must be free of other heavy jobs."""
    import re
    import subprocess
    description = (description or "").strip()
    if len(description) < 3:
        raise RuntimeError("describe the motion in a few words")
    seconds = max(1.0, min(float(seconds), 10.0))
    if name and not re.fullmatch(r"[a-z][a-z0-9_]{2,47}", name):
        raise RuntimeError("name must be 3-48 characters: lowercase letters, digits and underscores")
    script = SCRIPTS / "generate_skill.sh"
    if not script.exists():
        raise RuntimeError("text-to-motion generation is not installed (scripts/generate_skill.sh missing); see docs/MOTION_GENERATION.md")
    argv = [str(script), "--prompt", description, "--seconds", str(seconds), "--seed", str(int(seed))] + (["--name", name] if name else [])
    log = RUNTIME / "assistant-generate.log"
    with log.open("a") as stream:
        stream.write(f"=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {' '.join(argv)}\n")
        stream.flush()
        process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=stream, text=True, start_new_session=True)
    deadline = time.time() + 900
    while process.poll() is None and time.time() < deadline and not cancelled():
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
        raise RuntimeError("generation cancelled or timed out; see .runtime/assistant-generate.log")
    out = (process.stdout.read() or "").strip().splitlines()
    if process.returncode != 0:
        tail = "".join(log.read_text(errors="replace").splitlines(keepends=True)[-8:]).strip()
        raise RuntimeError(f"generation failed (exit {process.returncode}): {tail[-700:]}")
    try:
        record = json.loads(out[-1])
    except (ValueError, IndexError):
        raise RuntimeError("the generator did not report a skill record")
    return {"generated": True, **record, "note": "play it with play_skill; kinematic mode plays it exactly, physical mode asks the tracker to follow it"}


def list_characters() -> dict:
    """Skinned characters that can be rendered over the physical body (start_session(character=...))."""
    characters = [{"name": "", "title": "Mannequin (capsule body)", "licence": "built in"}]
    for path in sorted((RUNTIME / "characters").glob("*/character.json")):
        meta = _read_json(path, {}) or {}
        characters.append({"name": path.parent.name, "title": meta.get("name", path.parent.name), "licence": (meta.get("licence") or {}).get("name"),
                           "source": meta.get("source", {}).get("name")})
    return {"characters": characters}


TOOLS: dict[str, Callable] = {f.__name__: f for f in (
    describe_studio, describe_scene, start_session, end_session, get_state, walk_to, stop, pause, resume, reset, push, record,
    wait_until, list_skills, search_skills, get_skill, play_skill, run_sequence, save_sequence, attach_object, release_object, place_object,
    generate_skill, list_characters)}

TOOL_SPECS = [
    {"name": "describe_studio", "description": "Current live session, available scenes, controllers, skills and GPU lock. Call first.", "parameters": {"type": "object", "properties": {}}},
    {"name": "describe_scene", "description": "Objects, sizes and positions of a scene in scene metres (origin = spawn).",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "start_session", "description": "Start an interactive live session: controller (tracker = tracker-driven walker), optional scene, mode physical (physics, falls possible) or kinematic (exact playback, no falls), optional skinned character. Takes about a minute.",
     "parameters": {"type": "object", "properties": {"controller": {"type": "string", "default": "tracker"}, "scene": {"type": "string"}, "preview": {"type": "string", "default": "960x540"},
                                                     "mode": {"type": "string", "enum": ["physical", "kinematic"], "default": "physical"}, "character": {"type": "string"}}}},
    {"name": "end_session", "description": "End the live session cleanly (records the evidence).", "parameters": {"type": "object", "properties": {}}},
    {"name": "get_state", "description": "Latest character state: position, speed, state, phase, destination, distance.", "parameters": {"type": "object", "properties": {}}},
    {"name": "walk_to", "description": "Send the character to a point (frame spawn = scene metres from the spawn, world = terrain metres, local = x ahead / y left of the character) or, with object, to that object's approach point.",
     "parameters": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "frame": {"type": "string", "enum": ["spawn", "world", "local"], "default": "spawn"}, "object": {"type": "string"}}}},
    {"name": "stop", "description": "Stop walking and stand where the character is.", "parameters": {"type": "object", "properties": {}}},
    {"name": "pause", "description": "Freeze simulated time.", "parameters": {"type": "object", "properties": {}}},
    {"name": "resume", "description": "Continue after pause.", "parameters": {"type": "object", "properties": {}}},
    {"name": "reset", "description": "Return the character to the spawn point; required after a fall.", "parameters": {"type": "object", "properties": {}}},
    {"name": "push", "description": "Shove the character with a horizontal velocity impulse in m/s.",
     "parameters": {"type": "object", "properties": {"vx": {"type": "number"}, "vy": {"type": "number"}}, "required": ["vx", "vy"]}},
    {"name": "record", "description": "Start or stop a named recording segment.",
     "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["start", "stop"]}, "name": {"type": "string"}}, "required": ["action"]}},
    {"name": "wait_until", "description": "Wait until the character has arrived, is standing, has fallen, has stopped, finished its skill (skill_done) or its sequence (sequence_done); max 120 s.",
     "parameters": {"type": "object", "properties": {"condition": {"type": "string", "enum": ["arrived", "standing", "fallen", "stopped", "skill_done", "sequence_done"]}, "timeout_s": {"type": "number", "default": 20}}, "required": ["condition"]}},
    {"name": "list_skills", "description": "Every skill that can be played (built-ins, library clips, generated clips, saved sequences) with category, duration and entry/exit pose.", "parameters": {"type": "object", "properties": {}}},
    {"name": "search_skills", "description": "Find library skills by words (e.g. 'dance', 'wave', 'carry box', 'kneel') and optionally a category: locomotion, dance, gesture, idle, action, floor, generated, sequence.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": "string"}, "limit": {"type": "integer", "default": 12}}, "required": ["query"]}},
    {"name": "get_skill", "description": "Full metadata of one skill: measured motion, source, licence, provenance, sequence steps.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "play_skill", "description": "Play a skill in the live session by name: a library clip (loops, speed 0.25-2), a saved sequence, or walk_to / stand. wait=true blocks until it has finished.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "loops": {"type": "integer", "default": 1}, "speed": {"type": "number", "default": 1.0}, "wait": {"type": "boolean", "default": False},
                                                     "x": {"type": "number"}, "y": {"type": "number"}, "frame": {"type": "string"}, "object": {"type": "string"}}, "required": ["name"]}},
    {"name": "run_sequence", "description": "Run a list of steps in order in the live session: walk_to (x,y,frame or object), a clip skill id (loops, speed, attach {object, body, at_frame}, release {object, at_frame}), attach/release/place_object, wait (seconds), stand. The worker waits for each step to finish. wait=true blocks until the sequence ends.",
     "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object"}}, "name": {"type": "string"}, "wait": {"type": "boolean", "default": False}}, "required": ["steps"]}},
    {"name": "save_sequence", "description": "Save a sequence of steps as a reusable composite skill in the library.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["name", "description", "steps"]}},
    {"name": "attach_object", "description": "Make a scene object follow a hand from now on (a kinematic grasp).",
     "parameters": {"type": "object", "properties": {"object": {"type": "string"}, "body": {"type": "string", "enum": ["RightHand", "LeftHand"], "default": "RightHand"}}, "required": ["object"]}},
    {"name": "release_object", "description": "Stop a scene object following the hand; it stays where it is.",
     "parameters": {"type": "object", "properties": {"object": {"type": "string"}}, "required": ["object"]}},
    {"name": "place_object", "description": "Put a scene object at a point in scene metres (origin = spawn, z up).",
     "parameters": {"type": "object", "properties": {"object": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}}, "required": ["object", "x", "y", "z"]}},
    {"name": "generate_skill", "description": "Only when the user explicitly asks to create or generate a new motion: generate a clip from a text description with the local text-to-motion model and add it to the library as a skill (1-10 s; takes minutes). For walking, carrying or playing existing motions use walk_to, search_skills, play_skill and run_sequence instead.",
     "parameters": {"type": "object", "properties": {"description": {"type": "string"}, "seconds": {"type": "number", "default": 4}, "name": {"type": "string"}, "seed": {"type": "integer", "default": 0}}, "required": ["description"]}},
    {"name": "list_characters", "description": "Skinned characters available for start_session(character=...).", "parameters": {"type": "object", "properties": {}}},
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
- The skill library holds motion-capture clips (search_skills finds them by words) and saved sequences.
  play_skill plays a clip; run_sequence chains walk_to, clips and object attachments and is the way to do
  "walk to the cup and pick it up": walk_to(object="cup"), then a reaching/carrying clip with attach
  {object, body, at_frame}, then wherever the user wants it carried, then release. Save a sequence the
  user likes with save_sequence so it becomes a skill. Prefer existing library clips (search_skills) and
  the walker; call generate_skill only when the user explicitly asks to create or generate a new motion,
  because it takes minutes. Kinematic mode plays clips exactly; physical mode may fall on acrobatic clips.
- Only one GPU job runs at a time; starting a session takes about a minute. Do not end a session the
  user did not ask to end.
- Be brief in replies: say what you did and what the character is doing now. Report failures plainly.
"""
