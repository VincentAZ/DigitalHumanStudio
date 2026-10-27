"""Read-only project state: controllers, training runs, evaluations, live sessions, host status."""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from studio_app import ARTIFACTS, CONFIG, DIAGNOSTICS, GPU_LOCK, LIVE_POINTER, ROOT, SCRIPTS

STAMP_RE = re.compile(r"-(\d{8}T\d{6}Z?)$")
SETS = ("flat", "redirect", "push")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def read_jsonl(path: Path, tail: Optional[int] = None) -> list:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    if tail is not None:
        lines = lines[-tail:]
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def split_stamp(name: str):
    match = STAMP_RE.search(name)
    if not match:
        return name, ""
    return name[: match.start()], match.group(1)


def evidence_for(stamp: str, suffix: str) -> Path:
    return DIAGNOSTICS / f"{stamp}-milestone3-{suffix}"


def job_finished(evidence: Path) -> bool:
    return (evidence / "exit-code.txt").exists()


def human_stamp(stamp: str) -> str:
    if len(stamp) < 15:
        return stamp
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]} UTC"


@dataclass
class TrainingRun:
    name: str
    stage: str
    experiment: str
    stamp: str
    output_dir: Path
    results_dir: Path
    evidence_dir: Path
    outcome: dict = field(default_factory=dict)
    contract: dict = field(default_factory=dict)
    epochs: int = 0
    last: dict = field(default_factory=dict)
    sha256: str = ""

    @property
    def checkpoint(self) -> Path:
        return self.results_dir / "inference_last.ckpt"

    @property
    def last_ckpt(self) -> Path:
        return self.results_dir / "last.ckpt"

    @property
    def has_controller(self) -> bool:
        return self.checkpoint.exists() and (self.results_dir / "resolved_configs_inference.pt").exists()

    @property
    def running(self) -> bool:
        return self.evidence_dir.exists() and not job_finished(self.evidence_dir)

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        return self.outcome.get("status", "unknown" if not self.evidence_dir.exists() else "failed")

    @property
    def created(self) -> str:
        return human_stamp(self.stamp)

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "metrics.jsonl"


def list_training_runs() -> list[TrainingRun]:
    runs = []
    for directory in sorted(ARTIFACTS.glob("train-*")):
        base, stamp = split_stamp(directory.name)
        parts = base.split("-", 2)
        if len(parts) < 3:
            continue
        _, stage, experiment = parts
        results = directory / "results" / experiment
        evidence = evidence_for(stamp, f"train-{stage}")
        metrics = read_jsonl(directory / "metrics.jsonl")
        sha = ""
        try:
            for line in (evidence / "checkpoints.sha256").read_text().splitlines():
                if line.strip().endswith("inference_last.ckpt"):
                    sha = line.split()[0]
        except OSError:
            pass
        runs.append(TrainingRun(name=directory.name, stage=stage, experiment=experiment, stamp=stamp,
                                output_dir=directory, results_dir=results, evidence_dir=evidence,
                                outcome=read_json(evidence / "outcome.json", {}) or {},
                                contract=read_json(evidence / "train-contract.json", {}) or {},
                                epochs=len(metrics), last=metrics[-1] if metrics else {}, sha256=sha))
    return runs


def list_controllers() -> list[TrainingRun]:
    return [run for run in list_training_runs() if run.has_controller]


@dataclass
class Evaluation:
    name: str
    kind: str
    scenario_set: str
    mode: str
    label: str
    stamp: str
    output_dir: Path
    evidence_dir: Path
    measurements: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    contract: dict = field(default_factory=dict)

    @property
    def adapter_sha256(self) -> str:
        return self.contract.get("adapter_sha256", "") or ""

    @property
    def running(self) -> bool:
        return self.evidence_dir.exists() and not job_finished(self.evidence_dir)

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        return self.outcome.get("status", "unknown")

    @property
    def successes(self):
        return self.measurements.get("successes")

    @property
    def created(self) -> str:
        return human_stamp(self.stamp)

    def media(self) -> list[Path]:
        return sorted(self.output_dir.rglob("*.mp4"))


def list_evaluations() -> list[Evaluation]:
    evaluations = []
    for directory in sorted(ARTIFACTS.glob("eval-*")):
        base, stamp = split_stamp(directory.name)
        parts = base.split("-")
        if len(parts) < 4:
            continue
        kind, scenario_set, mode = parts[1], parts[2], parts[3]
        label = "-".join(parts[4:])
        evidence = evidence_for(stamp, f"eval-{base[len('eval-'):]}")
        evaluations.append(Evaluation(name=directory.name, kind=kind, scenario_set=scenario_set, mode=mode, label=label,
                                      stamp=stamp, output_dir=directory, evidence_dir=evidence,
                                      measurements=read_json(directory / "measurements.json", {}) or {},
                                      outcome=read_json(evidence / "outcome.json", {}) or {},
                                      contract=read_json(directory / "run-contract.json", {}) or {}))
    return evaluations


def best_scores(evaluations: list[Evaluation], sha256: str) -> dict:
    """Best accepted batch score per scenario set for one adapter checkpoint."""
    scores = {}
    for ev in evaluations:
        if ev.kind != "adapter" or not sha256 or ev.adapter_sha256 != sha256 or ev.mode != "batch":
            continue
        if ev.status != "passed" or ev.successes is None:
            continue
        current = scores.get(ev.scenario_set)
        if current is None or ev.successes > current.successes:
            scores[ev.scenario_set] = ev
    return scores


@dataclass
class LiveSession:
    name: str
    stamp: str
    output_dir: Path
    evidence_dir: Path
    summary: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.evidence_dir.exists() and not job_finished(self.evidence_dir)

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        return self.outcome.get("status", "unknown")

    @property
    def created(self) -> str:
        return human_stamp(self.stamp)


def list_live_sessions() -> list[LiveSession]:
    sessions = []
    for directory in sorted(ARTIFACTS.glob("live-*")):
        base, stamp = split_stamp(directory.name)
        evidence = evidence_for(stamp, base)
        sessions.append(LiveSession(name=directory.name, stamp=stamp, output_dir=directory, evidence_dir=evidence,
                                    summary=read_json(directory / "summary.json", {}) or {},
                                    outcome=read_json(evidence / "outcome.json", {}) or {}))
    return sessions


def _run(argv: list[str], timeout: float = 8.0) -> str:
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def gpu_status() -> dict:
    text = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"])
    if not text.strip():
        return {}
    fields = [part.strip() for part in text.strip().splitlines()[0].split(",")]
    keys = ["name", "utilization", "memory_used", "memory_total", "temperature", "power"]
    return dict(zip(keys, fields))


def running_containers() -> list[str]:
    text = _run([str(SCRIPTS / "docker.sh"), "ps", "--format", "{{.Names}}\t{{.Status}}"])
    return [line for line in text.splitlines() if line.strip()]


def gpu_lock_held() -> bool:
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


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def current_live_pointer() -> Optional[dict]:
    pointer = read_json(LIVE_POINTER)
    if not pointer:
        return None
    evidence = Path(pointer.get("evidence", ""))
    pointer["finished"] = job_finished(evidence) or not pid_alive(int(pointer.get("launcher_pid", 0) or 0))
    return pointer


def image_lock() -> str:
    try:
        return (CONFIG / "runtime-image.lock").read_text().strip()
    except OSError:
        return "missing"


def milestone_records() -> dict:
    return {name: read_json(CONFIG / f"{name}.json", {}) or {} for name in ("milestone1", "milestone3")}


def progress_headings(limit: int = 8) -> list[str]:
    try:
        lines = (ROOT / "PROGRESS.md").read_text().splitlines()
    except OSError:
        return []
    headings = [line[3:].strip() for line in lines if line.startswith("## ")]
    # Entries are grouped by milestone in the file; order newest first by their date prefix.
    return sorted(headings, key=lambda text: text[:10], reverse=True)[:limit]
