"""Bridge between the web interface (scripts/studio_app/web) and the project's back end.

Everything the page can do goes through this object over a Qt WebChannel: start and end live
sessions with the recorded launchers, append commands to the session's commands.jsonl, follow
state.json / frame.jpg / status.jsonl, run assistant turns, and read provider settings. Payloads
cross the channel as JSON strings in both directions.
"""
from __future__ import annotations

import datetime as dt
import getpass
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import PySide6
from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot, qVersion

from studio_app import DIAGNOSTICS, ROOT, SCRIPTS
from studio_app import state as st
from studio_app.jobs import JobCenter, docker_stop, open_path
from studio_assistant import TRANSCRIPTS
from studio_assistant.providers import (PROVIDERS, THINKING_LEVELS, key_status, list_models, load_config, make_assistant,
                                        provider_settings, save_config)
from studio_assistant.tools import CANCEL, call_tool
from studio_walk.skill_lib import list_skills as read_skill_folders

SKILLS_DIR = ROOT / "skills"
CHARACTERS_DIR = ROOT / ".runtime" / "characters"
PREVIEWS = ["640x480", "960x540", "1280x720"]
MODES = [{"id": "physical", "name": "Physical (tracker)", "description": "The tracker acts and physics decides; falls are possible."},
         {"id": "kinematic", "name": "Kinematic playback", "description": "The composed reference is played exactly: no tracking, no contact, no falls."}]
WALKER = {"id": "tracker", "name": "Tracker-driven walker", "category": "locomotion", "available": True, "duration": "continuous",
          "description": "Walk to a destination, turn, slow down and come to a stand. Milestone 1 tracker following licensed clips; no training.",
          "source": "Built in", "licence": "BONES-SEED clip licence recorded in config/milestone1-license.json", "tags": ["locomotion", "SOMA-23"]}


def _dumps(payload) -> str:
    return json.dumps(payload, default=str)


class StatusPoller(QThread):
    """Host status off the interface thread (nvidia-smi and docker take tens of milliseconds)."""
    status = Signal(dict)

    def run(self):
        self.status.emit({"gpu": st.gpu_status(), "containers": st.running_containers(), "lock": st.gpu_lock_held()})


class TurnWorker(QThread):
    event = Signal(str, dict)

    def __init__(self, assistant, text: str, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.text = text

    def run(self):
        try:
            self.assistant.run_turn(self.text, lambda kind, payload: self.event.emit(kind, payload))
        except Exception as error:  # the page shows the message; the turn always ends with "done"
            self.event.emit("error", {"message": str(error)})
            self.event.emit("done", {"text": ""})


class ToolWorker(QThread):
    """Runs one assistant tool off the interface thread (generation, sequences)."""
    result = Signal(str, dict)

    def __init__(self, label: str, name: str, arguments: dict, parent=None):
        super().__init__(parent)
        self.label, self.name, self.arguments = label, name, arguments

    def run(self):
        self.result.emit(self.label, call_tool(self.name, self.arguments))


class ModelsWorker(QThread):
    result = Signal(dict)

    def __init__(self, provider: str, key: str, base_url: str, parent=None):
        super().__init__(parent)
        self.provider, self.key, self.base_url = provider, key, base_url

    def run(self):
        try:
            self.result.emit({"provider": self.provider, "models": list_models(self.provider, self.key, self.base_url)})
        except Exception as error:
            self.result.emit({"provider": self.provider, "error": str(error)})


class Bridge(QObject):
    """The page polls ``poll(cursor, state_token)`` about 15 times a second; everything that happens in
    between (acknowledgements, session changes, host status, launcher output, assistant events) is
    queued as numbered events and returned in order. Qt-to-page signals are not used: their delivery
    proved unreliable across page reloads."""

    def __init__(self, jobs: JobCenter, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.jobs.log.connect(lambda text: self._push("job", {"text": text}))
        self.events: list[dict] = []
        self.seq = 0
        self.events_lock = threading.Lock()
        self.last_state: dict | None = None
        self.last_frame = ""
        self.pointer: dict | None = None
        self.phase = "none"
        self.launch_job = None
        self.launch_started = 0.0
        self._pending_stamp = None
        self._state_mtime = 0.0
        self._frame_mtime = 0.0
        self._status_lines = 0
        self._pointer_checks = 0
        self.assistant = None
        self.assistant_provider = ""
        self.worker: TurnWorker | None = None
        self.transcript_path: Path | None = None
        self.host_status: dict = {}
        self.poller = StatusPoller(self)
        self.poller.status.connect(self._host_status)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._poll_live)
        self.live_timer.start(33)
        self.host_timer = QTimer(self)
        self.host_timer.timeout.connect(lambda: self.poller.isRunning() or self.poller.start())
        self.host_timer.start(2000)
        self.poller.start()
        self._adopt_existing()

    def _push(self, kind: str, payload):
        with self.events_lock:
            self.seq += 1
            self.events.append({"seq": self.seq, "kind": kind, "payload": payload})
            del self.events[:-2000]

    @Slot(int, str, result=str)
    def poll(self, cursor: int, state_token: str) -> str:
        with self.events_lock:
            events = [e for e in self.events if e["seq"] > cursor]
            seq = self.seq
        payload = {"seq": seq, "events": events, "phase": self.phase, "frame": self.last_frame if self.phase == "running" else ""}
        token = str(self._state_mtime)
        if self.last_state is not None and token != state_token and self.phase == "running":
            payload["state"] = self.last_state
            payload["state_token"] = token
        return _dumps(payload)

    # ---- static information ---------------------------------------------------------------
    @Slot(result=str)
    def bootstrap(self) -> str:
        scenes = [{"id": "", "name": "Flat floor", "description": "Open floor, no objects", "items": [], "room_half_size": 6.0}]
        for path in sorted((st.CONFIG / "scenes").glob("*.json")):
            meta = st.read_json(path, {}) or {}
            scenes.append({"id": path.stem, "name": meta.get("name", path.stem).replace("_", " ").capitalize(),
                           "description": meta.get("description", ""), "items": meta.get("items", []), "objects": meta.get("objects", []),
                           "room_half_size": meta.get("room_half_size", 6.0)})
        controllers = [{"id": "tracker", "name": "Tracker-driven walker"}]
        for run in st.list_controllers():
            controllers.append({"id": str(run.results_dir), "name": f"{run.experiment} (retired trained adapter, {run.created})"})
        return _dumps({"scenes": scenes, "controllers": controllers, "previews": PREVIEWS, "modes": MODES, "characters": self._characters(),
                       "providers": [{"id": name, "title": meta["title"].split(" (")[0]} for name, meta in PROVIDERS.items()],
                       "thinking_levels": THINKING_LEVELS, "user": getpass.getuser(), "root": str(ROOT),
                       "skills": self._skills(), "project": self._project_facts(), "session": self._session_payload(), "seq": self.seq,
                       "host": self._host_payload(), "generation_available": (SCRIPTS / "generate_skill.sh").exists()})

    def _skills(self) -> list[dict]:
        skills = [WALKER]
        for meta in read_skill_folders(SKILLS_DIR):
            folder = SKILLS_DIR / meta["id"]
            thumb, preview = folder / "thumbnail.png", folder / "preview.gif"
            licence = meta.get("licence")
            source = meta.get("source") or {}
            provenance = meta.get("provenance") or {}
            skills.append({"id": meta["id"], "name": meta.get("name", meta["id"]), "kind": meta.get("kind", "clip"),
                           "category": meta.get("category", "library"), "available": False,
                           "duration": f"{meta['duration_s']:.1f} s" if meta.get("duration_s") else "", "duration_s": meta.get("duration_s"),
                           "description": meta.get("description", ""), "tags": meta.get("tags", []), "loop": meta.get("loop", False),
                           "entry_pose": meta.get("entry_pose", ""), "exit_pose": meta.get("exit_pose", ""), "travel_m": meta.get("travel_m"),
                           "turn_deg": meta.get("turn_deg"), "frames": meta.get("frames"), "steps": meta.get("steps"),
                           "source": provenance.get("dataset") or source.get("kind", "") or "", "licence": licence.get("name", "") if isinstance(licence, dict) else (licence or "not recorded"),
                           "licence_url": licence.get("url", "") if isinstance(licence, dict) else "", "attribution": licence.get("attribution", "") if isinstance(licence, dict) else "",
                           "provenance": provenance, "clip": source.get("clip", ""),
                           "thumbnail": QUrl.fromLocalFile(str(thumb)).toString() if thumb.exists() else "",
                           "preview": QUrl.fromLocalFile(str(preview)).toString() if preview.exists() else "",
                           "folder": str(folder)})
        return skills

    @staticmethod
    def _characters() -> list[dict]:
        characters = [{"id": "", "name": "Mannequin (capsule body)", "licence": "built in", "source": "SOMA-23 physics body", "description": "The physical body as it is simulated."}]
        for path in sorted(CHARACTERS_DIR.glob("*/character.json")):
            meta = st.read_json(path, {}) or {}
            thumb = path.parent / "thumbnail.png"
            characters.append({"id": path.parent.name, "name": meta.get("name", path.parent.name), "licence": (meta.get("licence") or {}).get("name", ""),
                               "licence_url": (meta.get("licence") or {}).get("url", ""), "source": (meta.get("source") or {}).get("name", ""),
                               "source_url": (meta.get("source") or {}).get("url", ""), "description": meta.get("description", ""),
                               "vertices": meta.get("vertices"), "joints": meta.get("joints"), "mapped": meta.get("mapped_bodies"), "unmapped": meta.get("unmapped_bodies", []),
                               "thumbnail": QUrl.fromLocalFile(str(thumb)).toString() if thumb.exists() else ""})
        return characters

    @Slot(result=str)
    def listCharacters(self) -> str:
        return _dumps(self._characters())

    def _project_facts(self) -> dict:
        records = st.milestone_records()
        return {"root": str(ROOT), "image": st.image_lock(), "python": sys.version.split()[0], "qt": qVersion(), "pyside": PySide6.__version__,
                "milestone1": (records.get("milestone1") or {}).get("status", "not recorded"),
                "milestone3": (records.get("milestone3") or {}).get("status", "not accepted (three RL attempts; tuning stopped 2026-10-27)"),
                "progress": st.progress_headings(6), "sessions": self._recent_sessions()}

    @staticmethod
    def _recent_sessions(limit: int = 8) -> list[dict]:
        sessions = sorted(st.list_live_sessions(), key=lambda s: s.stamp, reverse=True)[:limit]
        return [{"name": s.name, "created": s.created, "status": s.status, "steps": s.summary.get("steps"), "output": str(s.output_dir),
                 "scene": (st.read_json(s.output_dir / "scene.json", {}) or {}).get("name") or "flat", "controller": s.summary.get("controller", "")} for s in sessions]

    @Slot(result=str)
    def projectFacts(self) -> str:
        return _dumps(self._project_facts())

    @Slot(result=str)
    def listSkills(self) -> str:
        return _dumps(self._skills())

    # ---- host status ------------------------------------------------------------------------
    def _host_status(self, status: dict):
        self.host_status = status
        self._push("host", self._host_payload())

    def _host_payload(self) -> dict:
        status = dict(self.host_status)
        status["jobs"] = [job.label for job in self.jobs.active()]
        status["busy"] = bool(status.get("lock") or status["jobs"] or self.phase in ("starting", "running"))
        return status

    # ---- live session ----------------------------------------------------------------------
    def _session_payload(self, message: str = "", outcome: dict | None = None) -> dict:
        payload = {"phase": self.phase, "message": message, "outcome": outcome or {}}
        if self.pointer:
            output = Path(self.pointer["output"])
            scene = st.read_json(output / "scene.json", {}) or {}
            payload.update({"name": output.name, "output": str(output), "evidence": self.pointer.get("evidence", ""),
                            "container": self.pointer.get("container", ""), "started_utc": self.pointer.get("started_utc", ""),
                            "controller": self.pointer.get("controller_dir", ""), "scene": scene.get("name", "") or "",
                            "mode": self.pointer.get("mode", "physical"), "character": self.pointer.get("character", ""),
                            "scene_items": scene.get("items", []), "scene_objects": scene.get("objects", []), "recording": str(output / "performance.mp4")})
        return payload

    def _emit_session(self, message: str = "", outcome: dict | None = None):
        self._push("session", self._session_payload(message, outcome))

    def _adopt_existing(self):
        pointer = st.current_live_pointer()
        if pointer and not pointer["finished"]:
            self._attach(pointer)

    def _attach(self, pointer: dict):
        self.pointer = pointer
        self.phase = "starting"
        self._state_mtime = self._frame_mtime = 0.0
        self._status_lines = 0
        self.last_state = None
        self.last_frame = ""
        self._emit_session("Isaac is starting in the worker container")

    @Slot(str, str, str, str, str, result=str)
    def startSession(self, controller: str, scene: str, preview: str, mode: str = "physical", character: str = "") -> str:
        if self.phase in ("starting", "running"):
            return "A session is already running."
        if self.jobs.active() or st.gpu_lock_held():
            return "Another studio GPU job is running. One heavy GPU job at a time."
        if preview not in PREVIEWS:
            return f"Unknown preview size {preview}."
        if mode not in ("physical", "kinematic"):
            return f"Unknown mode {mode}."
        if mode == "kinematic" and (controller or "tracker") != "tracker":
            return "Kinematic playback needs the tracker-driven walker's reference composer."
        if character and not (CHARACTERS_DIR / character / "character.json").exists():
            return f"Unknown character {character}."
        argv = [str(SCRIPTS / "run_milestone3_live.sh"), controller or "tracker", "--interactive", "--preview", preview, "--label", "studio", "--mode", mode]
        if scene:
            if not (st.CONFIG / "scenes" / f"{scene}.json").exists():
                return f"Unknown scene {scene}."
            argv += ["--scene", scene]
        if character:
            argv += ["--character", character]
        before = st.current_live_pointer()
        self._pending_stamp = before.get("started_utc") if before else None
        self.pointer = None
        self.phase = "starting"
        self.launch_started = time.time()
        self.launch_job = self.jobs.start("live session", argv)
        self._emit_session("Launching the recorded live-session launcher")
        QTimer.singleShot(500, self._wait_pointer)
        return ""

    def _wait_pointer(self):
        if self.pointer is not None or self.phase != "starting":
            return
        pointer = st.current_live_pointer()
        if pointer and pointer.get("started_utc") != self._pending_stamp and not pointer["finished"]:
            self._attach(pointer)
            return
        if not self.jobs.active():
            tail = "\n".join(self.launch_job.lines[-4:]) if self.launch_job else ""
            self.phase = "failed"
            self._emit_session(f"The launcher exited before a session started. {tail}".strip())
            return
        QTimer.singleShot(500, self._wait_pointer)

    @Slot(result=str)
    def endSession(self) -> str:
        return self.sendCommand(json.dumps({"cmd": "quit"}))

    @Slot(result=str)
    def forceStop(self) -> str:
        if not self.pointer:
            return "No session to stop."
        return docker_stop(self.pointer["container"]) or "stop requested"

    @Slot(str, result=str)
    def sendCommand(self, command_json: str) -> str:
        if not self.pointer or self.phase != "running":
            return "No running session."
        try:
            command = json.loads(command_json)
        except ValueError:
            return "Malformed command."
        command["issued_wall_time"] = time.time()
        try:
            with (Path(self.pointer["output"]) / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps(command) + "\n")
        except OSError as error:
            return f"Could not write the command: {error}"
        return ""

    def _poll_live(self):
        if not self.pointer:
            self._pointer_checks += 1
            if self._pointer_checks % 30 == 0 and self.phase not in ("starting",):
                self._adopt_existing()
            return
        output = Path(self.pointer["output"])
        live = output / "live"
        try:
            state_mtime = (live / "state.json").stat().st_mtime
        except OSError:
            state_mtime = 0.0
        if state_mtime and state_mtime != self._state_mtime:
            state = st.read_json(live / "state.json")
            if state:
                self._state_mtime = state_mtime
                self.last_state = state
                if self.phase != "running":
                    self.phase = "running"
                    self._emit_session("Session running")
        try:
            frame_mtime = (live / "frame.jpg").stat().st_mtime_ns
        except OSError:
            frame_mtime = 0
        if frame_mtime and frame_mtime != self._frame_mtime:
            self._frame_mtime = frame_mtime
            self.last_frame = QUrl.fromLocalFile(str(live / "frame.jpg")).toString() + f"?t={frame_mtime}"
        records = st.read_jsonl(output / "status.jsonl")
        if len(records) > self._status_lines:
            for record in records[self._status_lines:]:
                self._push("ack", record)
            self._status_lines = len(records)
        if st.job_finished(Path(self.pointer["evidence"])):
            outcome = st.read_json(Path(self.pointer["evidence"]) / "outcome.json", {}) or {}
            self.phase = "ended" if outcome.get("status") == "passed" else "failed"
            self._emit_session(f"Session ended: {outcome.get('status', 'unknown')} after {outcome.get('steps', '?')} steps", outcome)
            self.pointer = None
            self.last_state = None
            self.last_frame = ""

    # ---- resources -------------------------------------------------------------------------
    @Slot(str, result=str)
    def openResource(self, name: str) -> str:
        targets = {"plan": ROOT / "IMPLEMENTATION_PLAN.md", "direction": ROOT / "docs" / "DIRECTION.md", "progress": ROOT / "PROGRESS.md",
                   "diagnostics": DIAGNOSTICS, "workspace": ROOT, "sessions": ROOT / "artifacts" / "milestone3"}
        if name == "mixar":
            try:
                subprocess.Popen([str(SCRIPTS / "mixar.sh")], cwd=ROOT, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as error:
                return f"Mixar launch failed: {error}"
            return ""
        if name.startswith("path:"):
            path = Path(name[5:])
            if not path.exists():
                return f"{path} does not exist"
            open_path(path)
            return ""
        if name not in targets:
            return f"Unknown resource {name}"
        open_path(targets[name])
        return ""

    @Slot(str, str, result=str)
    def playSkill(self, name: str, arguments_json: str) -> str:
        try:
            arguments = json.loads(arguments_json or "{}")
            return _dumps(call_tool("play_skill", {"name": name, **arguments}))
        except Exception as error:
            return _dumps({"error": str(error)})

    @Slot(str, str, result=str)
    def runSequence(self, name: str, steps_json: str) -> str:
        try:
            return _dumps(call_tool("run_sequence", {"steps": json.loads(steps_json), "name": name}))
        except Exception as error:
            return _dumps({"error": str(error)})

    @Slot(str, str, str, result=str)
    def saveSequence(self, name: str, description: str, steps_json: str) -> str:
        try:
            result = call_tool("save_sequence", {"name": name, "description": description, "steps": json.loads(steps_json)})
        except Exception as error:
            return _dumps({"error": str(error)})
        if "error" not in result:
            self._push("skills", self._skills())
        return _dumps(result)

    @Slot(result=str)
    def refreshSkills(self) -> str:
        skills = self._skills()
        self._push("skills", skills)
        return _dumps(skills)

    @Slot(str, str, result=str)
    def skillAction(self, action: str, skill: str) -> str:
        """Open a skill's folder or preview, or forget a generated/composed skill (shipped clips are kept)."""
        folder = SKILLS_DIR / skill
        if not (folder / "skill.json").exists():
            return "Unknown skill."
        if action == "open":
            open_path(folder)
            return ""
        if action == "delete":
            meta = st.read_json(folder / "skill.json", {}) or {}
            if (meta.get("provenance") or {}).get("generated_by") == "scripts/build_skill_catalog.py":
                return "Shipped clips are part of the catalog; rebuild it with scripts/build_skill_catalog.sh instead."
            import shutil
            shutil.rmtree(folder)
            self._push("skills", self._skills())
            return ""
        return "Unknown action."

    @Slot(str, float, str, int, result=str)
    def generateSkill(self, description: str, seconds: float, name: str, seed: int) -> str:
        if getattr(self, "generation_worker", None) is not None and self.generation_worker.isRunning():
            return "A generation is already running."
        if not (SCRIPTS / "generate_skill.sh").exists():
            return "Text-to-motion generation is not installed (see docs/MOTION_GENERATION.md)."
        self.generation_worker = ToolWorker("generation", "generate_skill", {"description": description, "seconds": seconds, "name": name, "seed": seed}, self)
        self.generation_worker.result.connect(self._tool_result)
        self.generation_worker.start()
        self._push("generation", {"status": "running", "description": description, "seconds": seconds})
        return ""

    def _tool_result(self, label: str, result: dict):
        if label == "generation":
            self._push("generation", {"status": "failed" if "error" in result else "done", **result})
            if "error" not in result:
                self._push("skills", self._skills())

    # ---- providers --------------------------------------------------------------------------
    @Slot(str, result=str)
    def providerInfo(self, name: str) -> str:
        if name not in PROVIDERS:
            return _dumps({"error": f"unknown provider {name}"})
        settings = provider_settings(name)
        stored = bool(load_config().get(name, {}).get("api_key"))
        return _dumps({"id": name, "title": PROVIDERS[name]["title"], "kind": settings["kind"], "key_status": key_status(name),
                       "has_key": bool(settings.get("api_key")), "stored_key": stored, "key_optional": bool(settings.get("key_optional")),
                       "model": settings.get("model", ""), "models": settings.get("models", []), "thinking": settings.get("thinking", "default"),
                       "base_url": settings.get("base_url", ""), "env": settings.get("env", "")})

    @Slot(str, str, result=str)
    def saveProvider(self, name: str, settings_json: str) -> str:
        if name not in PROVIDERS:
            return f"unknown provider {name}"
        try:
            incoming = json.loads(settings_json)
        except ValueError:
            return "malformed settings"
        config = load_config()
        entry = config.get(name, {})
        if incoming.get("api_key", "").strip():
            entry["api_key"] = incoming["api_key"].strip()
        entry["model"] = incoming.get("model", "").strip()
        if incoming.get("thinking") in THINKING_LEVELS:
            entry["thinking"] = incoming["thinking"]
        if incoming.get("base_url", "").strip():
            entry["base_url"] = incoming["base_url"].strip()
        config[name] = entry
        save_config(config)
        if name == self.assistant_provider:
            self.assistantNew()   # settings apply to the next conversation
        return ""

    @Slot(str)
    def forgetKey(self, name: str):
        config = load_config()
        config.get(name, {}).pop("api_key", None)
        save_config(config)

    @Slot(str, str, str)
    def fetchModels(self, name: str, key: str, base_url: str):
        worker = ModelsWorker(name, key, base_url, self)
        worker.result.connect(self._models_result)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _models_result(self, payload: dict):
        self._push("models", payload)

    # ---- assistant --------------------------------------------------------------------------
    @Slot(str, str, result=str)
    def assistantSend(self, provider: str, text: str) -> str:
        text = text.strip()
        if not text:
            return "Nothing to send."
        if self.worker is not None and self.worker.isRunning():
            return "The assistant is still working; press Stop first."
        if self.assistant is None or provider != self.assistant_provider:
            self.assistantNew()
            try:
                self.assistant = make_assistant(provider)
            except Exception as error:
                return str(error)
            self.assistant_provider = provider
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            folder = TRANSCRIPTS / f"{stamp}-{provider}"
            folder.mkdir(parents=True, exist_ok=True)
            self.transcript_path = folder / "transcript.jsonl"
        self._log({"kind": "user", "text": text})
        CANCEL.clear()
        self.worker = TurnWorker(self.assistant, text, self)
        self.worker.event.connect(self._assistant_event)
        self.worker.start()
        return ""

    @Slot()
    def assistantStop(self):
        CANCEL.set()

    @Slot()
    def assistantNew(self):
        if self.assistant is not None and hasattr(self.assistant, "close"):
            try:
                self.assistant.close()
            except Exception:
                pass
        self.assistant = None
        self.assistant_provider = ""
        self.transcript_path = None

    def _log(self, record: dict):
        if self.transcript_path:
            with self.transcript_path.open("a") as stream:
                stream.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), **record}, default=str) + "\n")

    def _assistant_event(self, kind: str, payload: dict):
        self._log({"kind": kind, **payload})
        self._push("assistant", {"kind": kind, **payload})
