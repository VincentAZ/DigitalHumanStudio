"""Main window of the Digital Human Studio control center."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QPlainTextEdit, QTabWidget

from studio_app import ROOT
from studio_app import state as st
from studio_app.evaluation import EvaluationView
from studio_app.jobs import JobCenter
from studio_app.live import LiveView
from studio_app.project import ProjectView
from studio_app.skills import SkillsView
from studio_app.training import TrainingView


class StatusPoller(QThread):
    """Collect host status off the interface thread (nvidia-smi and docker take tens of milliseconds)."""
    status = Signal(dict)

    def run(self):
        self.status.emit({"gpu": st.gpu_status(), "containers": st.running_containers(), "lock": st.gpu_lock_held()})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Human Studio — control center")
        self.resize(1500, 980)
        self.jobs = JobCenter(self)
        self.tabs = QTabWidget()
        self.project = ProjectView()
        self.skills = SkillsView()
        self.training = TrainingView(self.jobs)
        self.live = LiveView(self.jobs)
        self.evaluation = EvaluationView(self.jobs)
        for widget, title in ((self.live, "Live scene"), (self.training, "Training"), (self.skills, "Skills"),
                              (self.evaluation, "Evaluation"), (self.project, "Project")):
            self.tabs.addTab(widget, title)
        self.setCentralWidget(self.tabs)
        self.skills.use_in_live.connect(self._direct)
        self.skills.evaluate.connect(self._evaluate)
        self.jobs.changed.connect(self._jobs_changed)
        dock = QDockWidget("Job output (launchers run here; full log in .runtime/studio-app.log)", self)
        self.job_log = QPlainTextEdit()
        self.job_log.setReadOnly(True)
        self.job_log.setMaximumBlockCount(2000)
        dock.setWidget(self.job_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [150], Qt.Orientation.Vertical)
        self.jobs.log.connect(self._append_log)
        self.poller = StatusPoller(self)
        self.poller.status.connect(self._status)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._poll_status)
        self.status_timer.start(2000)
        self._poll_status()

    def _poll_status(self):
        if not self.poller.isRunning():
            self.poller.start()

    def _status(self, status: dict):
        gpu = status["gpu"]
        gpu_text = "GPU: unavailable" if not gpu else f"GPU {gpu['utilization']}% · {gpu['memory_used']}/{gpu['memory_total']} MiB · {gpu['temperature']} °C"
        jobs = ", ".join(job.label for job in self.jobs.active()) or "none"
        containers = len(status["containers"])
        self.statusBar().showMessage(f"{gpu_text}   |   studio lock: {'held' if status['lock'] else 'free'}   |   "
                                     f"containers: {containers}   |   interface jobs: {jobs}   |   {ROOT}")

    def _append_log(self, text: str):
        self.job_log.moveCursor(self.job_log.textCursor().MoveOperation.End)
        self.job_log.insertPlainText(text)
        self.job_log.moveCursor(self.job_log.textCursor().MoveOperation.End)

    def _jobs_changed(self):
        for view in (self.training, self.evaluation, self.skills):
            view.refresh()
        self.live.refresh_controllers()

    def _direct(self, run):
        self.live.select_controller(run.results_dir)
        self.tabs.setCurrentWidget(self.live)

    def _evaluate(self, run):
        self.evaluation.select_controller(run.results_dir)
        self.tabs.setCurrentWidget(self.evaluation)

    def closeEvent(self, event):
        active = self.jobs.active()
        if active:
            from PySide6.QtWidgets import QMessageBox
            answer = QMessageBox.question(self, "Jobs still running",
                                          "Launchers started from this window keep running after it closes and record their own evidence. Close anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for job in active:
                job.process.setParent(None)
        event.accept()


def run(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("Digital Human Studio")
    window = MainWindow()
    window.show()
    return app.exec()
