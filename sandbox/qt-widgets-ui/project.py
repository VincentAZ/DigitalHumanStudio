"""Project view: host status, locked runtime, milestones, tools."""
from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

import PySide6
from PySide6.QtCore import qVersion

from studio_app import DIAGNOSTICS, ROOT, RUNTIME, SCRIPTS
from studio_app import state as st
from studio_app.jobs import open_path


class ProjectView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(4000)

    def _build(self):
        root = QVBoxLayout(self)
        facts = QGroupBox("Project")
        form = QFormLayout(facts)
        self.labels = {}
        for key, title in (("root", "Workspace"), ("image", "Locked runtime image"), ("python", "Interface Python"),
                           ("qt", "PySide6 / Qt"), ("gpu", "GPU"), ("containers", "Running containers"), ("lock", "Studio GPU lock"),
                           ("m1", "Milestone 1"), ("m3", "Milestone 3")):
            label = QLabel("–")
            label.setWordWrap(True)
            label.setTextInteractionFlags(label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
            self.labels[key] = label
            form.addRow(title, label)
        root.addWidget(facts)
        tools = QHBoxLayout()
        mixar = QPushButton("Launch Mixar")
        mixar.clicked.connect(self.launch_mixar)
        progress = QPushButton("Open PROGRESS.md")
        progress.clicked.connect(lambda: open_path(ROOT / "PROGRESS.md"))
        plan = QPushButton("Open implementation plan")
        plan.clicked.connect(lambda: open_path(ROOT / "IMPLEMENTATION_PLAN.md"))
        diagnostics = QPushButton("Open diagnostics folder")
        diagnostics.clicked.connect(lambda: open_path(DIAGNOSTICS))
        for widget in (mixar, progress, plan, diagnostics):
            tools.addWidget(widget)
        tools.addStretch(1)
        root.addLayout(tools)
        root.addWidget(QLabel("Latest progress-log entries"))
        self.progress = QPlainTextEdit()
        self.progress.setReadOnly(True)
        root.addWidget(self.progress, 1)

    def refresh(self):
        self.labels["root"].setText(str(ROOT))
        self.labels["image"].setText(st.image_lock())
        self.labels["python"].setText(f"{sys.executable} ({sys.version.split()[0]})")
        self.labels["qt"].setText(f"PySide6 {PySide6.__version__} / Qt {qVersion()}")
        gpu = st.gpu_status()
        self.labels["gpu"].setText("nvidia-smi unavailable" if not gpu else
                                   f"{gpu['name']} · {gpu['utilization']}% · {gpu['memory_used']}/{gpu['memory_total']} MiB · {gpu['temperature']} °C · {gpu['power']} W")
        containers = st.running_containers()
        self.labels["containers"].setText("none" if not containers else "\n".join(containers))
        self.labels["lock"].setText("held by a running studio job" if st.gpu_lock_held() else "free")
        records = st.milestone_records()
        m1 = records.get("milestone1", {})
        m3 = records.get("milestone3", {})
        self.labels["m1"].setText(f"status: {m1.get('status', 'not recorded')}" if m1 else "not recorded")
        self.labels["m3"].setText(f"status: {m3.get('status', 'not recorded')}" if m3 else "not accepted: three training attempts recorded, 90/100 gates not met")
        self.progress.setPlainText("\n".join(st.progress_headings()))

    def launch_mixar(self):
        try:
            subprocess.Popen([str(SCRIPTS / "mixar.sh")], cwd=ROOT, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            self.labels["containers"].setText(f"Mixar launch failed: {error}")
