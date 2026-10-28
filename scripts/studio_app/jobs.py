"""Launch and follow the project's recorded launchers from the interface."""
from __future__ import annotations

import datetime as dt
import os
import signal
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from studio_app import APP_LOG, ROOT, RUNTIME, SCRIPTS
from studio_app.state import pid_alive


class LauncherJob(QObject):
    """A launcher started in its own session outside the app's process tree, so closing the window
    neither kills it nor breaks its output pipe: it finishes and records its evidence either way.
    Its output goes to a log file that the job follows while the app is open."""
    output = Signal(str)
    finished = Signal(int)

    def __init__(self, label: str, argv: list[str], parent=None):
        super().__init__(parent)
        self.label = label
        self.argv = [str(part) for part in argv]
        self.started_at = dt.datetime.now(dt.timezone.utc)
        self.exit_code = None
        stamp = self.started_at.strftime("%Y%m%dT%H%M%SZ")
        self.log_path = RUNTIME / "launchers" / f"{stamp}-{label.replace(' ', '-')}.log"
        self.code_path = self.log_path.with_suffix(".exit")
        self.pid = 0
        self._offset = 0
        self._pending = ""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._follow)
        self.lines: list[str] = []

    def start(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        wrapper = 'log=$1 code=$2; shift 2; "$@" >"$log" 2>&1 </dev/null; printf "%s\\n" "$?" >"$code"'
        started, self.pid = QProcess.startDetached("setsid", ["--wait", "bash", "-c", wrapper, "launcher",
                                                              str(self.log_path), str(self.code_path), *self.argv], str(ROOT))
        if not started:
            self.exit_code = -1
            self.lines.append("Could not start the launcher.")
            QTimer.singleShot(0, lambda: self.finished.emit(-1))
            return
        self.timer.start(250)

    @property
    def running(self) -> bool:
        return self.exit_code is None and self.pid > 0

    def terminate(self):
        """Ask the launcher's whole session to stop (only before a session pointer exists)."""
        try:
            os.killpg(os.getpgid(self.pid), signal.SIGTERM)
        except OSError:
            pass

    def _follow(self):
        try:
            with self.log_path.open("rb") as stream:
                stream.seek(self._offset)
                data = stream.read()
        except OSError:
            data = b""
        if data:
            self._offset += len(data)
            text = data.decode("utf-8", errors="replace")
            self.lines.extend((self._pending + text).splitlines())
            self._pending = "" if text.endswith("\n") else self.lines.pop()
            del self.lines[:-2000]
            self.output.emit(text)
        if self.code_path.exists():
            code = self.code_path.read_text().strip()
            self._done(int(code) if code.lstrip("-").isdigit() else -1)
        elif not pid_alive(self.pid):
            self._done(-1)

    def _done(self, code: int):
        self.timer.stop()
        if self._pending:
            self.lines.append(self._pending)
            self._pending = ""
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
