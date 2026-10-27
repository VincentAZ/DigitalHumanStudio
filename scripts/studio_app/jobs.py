"""Launch and follow the project's recorded launchers from the interface."""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from studio_app import APP_LOG, ROOT, SCRIPTS


class LauncherJob(QObject):
    output = Signal(str)
    finished = Signal(int)

    def __init__(self, label: str, argv: list[str], parent=None):
        super().__init__(parent)
        self.label = label
        self.argv = [str(part) for part in argv]
        self.started_at = dt.datetime.now(dt.timezone.utc)
        self.exit_code = None
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.lines: list[str] = []

    def start(self):
        self.process.start(self.argv[0], self.argv[1:])

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def _read(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not text:
            return
        self.lines.extend(text.splitlines())
        del self.lines[:-2000]
        self.output.emit(text)

    def _finished(self, code: int, _status):
        self.exit_code = code
        self.finished.emit(code)


class JobCenter(QObject):
    """One GPU launcher at a time; the launchers themselves also take the GPU lock."""
    changed = Signal()
    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[LauncherJob] = []

    def active(self) -> list[LauncherJob]:
        return [job for job in self.jobs if job.running]

    def start(self, label: str, argv: list[str]) -> LauncherJob:
        job = LauncherJob(label, argv, self)
        job.output.connect(lambda text, job=job: self._relay(job, text))
        job.finished.connect(lambda code, job=job: self._done(job, code))
        self.jobs.append(job)
        self._append_log(f"=== START {label}: {' '.join(job.argv)}\n")
        job.start()
        self.changed.emit()
        return job

    def _relay(self, job: LauncherJob, text: str):
        self._append_log(text)
        self.log.emit(text)

    def _done(self, job: LauncherJob, code: int):
        self._append_log(f"=== END {job.label}: exit {code}\n")
        self.log.emit(f"=== {job.label} finished with exit code {code}\n")
        self.changed.emit()

    def _append_log(self, text: str):
        try:
            APP_LOG.parent.mkdir(parents=True, exist_ok=True)
            with APP_LOG.open("a") as stream:
                stream.write(text)
        except OSError:
            pass


def docker_stop(container: str) -> str:
    """Hard stop of a studio container; the launcher records the failure evidence."""
    try:
        completed = subprocess.run([str(SCRIPTS / "docker.sh"), "stop", "--timeout", "20", container],
                                   capture_output=True, text=True, timeout=60, cwd=ROOT)
        return (completed.stdout + completed.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)


def open_path(path: Path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
