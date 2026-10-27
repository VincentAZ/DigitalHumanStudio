"""Evaluation view: reserved-scenario results and launching new evaluations."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from studio_app import SCRIPTS
from studio_app import state as st
from studio_app.jobs import JobCenter, open_path

COLUMNS = ["started", "controller", "set", "mode", "label", "successes /100", "arrived ≤15 s", "falls", "gate 90", "run status"]


class EvaluationView(QWidget):
    def __init__(self, jobs: JobCenter, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.evaluations: list[st.Evaluation] = []
        self.controllers: list[st.TrainingRun] = []
        self.selected: st.Evaluation | None = None
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

    def _build(self):
        root = QVBoxLayout(self)
        launch = QGroupBox("Evaluate on the reserved scenarios (100 trials, scripts/run_milestone3_eval.sh)")
        form = QFormLayout(launch)
        self.kind = QComboBox()
        self.kind.addItems(["adapter", "prior"])
        self.controller = QComboBox()
        self.scenario = QComboBox()
        self.scenario.addItems(list(st.SETS))
        self.seed = QSpinBox()
        self.seed.setRange(0, 9999)
        self.label = QLineEdit()
        self.label.setPlaceholderText("label for the evidence folder (optional)")
        self.record = QLineEdit()
        self.record.setPlaceholderText("trial ids to record on video, e.g. 0,1,2 (optional, slower)")
        self.temperature = QLineEdit()
        self.temperature.setPlaceholderText("token temperature override (optional)")
        self.start_button = QPushButton("Start evaluation")
        self.start_button.clicked.connect(self.start)
        form.addRow("Controller kind", self.kind)
        form.addRow("Adapter / task config", self.controller)
        form.addRow("Scenario set", self.scenario)
        form.addRow("Seed", self.seed)
        form.addRow("Label", self.label)
        form.addRow("Record trials", self.record)
        form.addRow("Temperature", self.temperature)
        form.addRow(self.start_button)
        root.addWidget(launch)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._select)
        root.addWidget(self.table, 2)

        actions = QHBoxLayout()
        self.detail_label = QLabel("select an evaluation")
        self.topdown_button = QPushButton("Open top-down plot")
        self.topdown_button.clicked.connect(self._open_topdown)
        self.video_button = QPushButton("Open recorded video")
        self.video_button.clicked.connect(self._open_video)
        self.folder_button = QPushButton("Open results folder")
        self.folder_button.clicked.connect(lambda: self.selected and open_path(self.selected.output_dir))
        for widget in (self.detail_label, self.topdown_button, self.video_button, self.folder_button):
            actions.addWidget(widget)
        actions.addStretch(1)
        root.addLayout(actions)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        root.addWidget(self.detail, 1)

    def refresh(self):
        self.controllers = st.list_controllers()
        current = self.controller.currentData()
        self.controller.blockSignals(True)
        self.controller.clear()
        for run in self.controllers:
            self.controller.addItem(f"{run.experiment} ({run.created})", str(run.results_dir))
        if current:
            index = self.controller.findData(current)
            if index >= 0:
                self.controller.setCurrentIndex(index)
        self.controller.blockSignals(False)
        selected_name = self.selected.name if self.selected else None
        self.evaluations = sorted(st.list_evaluations(), key=lambda ev: ev.stamp, reverse=True)
        sha_to_name = {run.sha256: run.experiment for run in self.controllers if run.sha256}
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.evaluations))
        for row, ev in enumerate(self.evaluations):
            m = ev.measurements
            name = "prior (unadapted)" if ev.kind == "prior" else sha_to_name.get(ev.adapter_sha256, ev.adapter_sha256[:12] or "?")
            gate = m.get("gate_passed_90_percent")
            values = [ev.created, name, ev.scenario_set, ev.mode, ev.label, m.get("successes", "–"), m.get("arrived_within_15s", "–"),
                      m.get("falls", "–"), "–" if gate is None else ("yes" if gate else "no"), ev.status]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 8 and gate is not None:
                    item.setForeground(Qt.GlobalColor.darkGreen if gate else Qt.GlobalColor.darkRed)
                self.table.setItem(row, column, item)
            if ev.name == selected_name:
                self.table.selectRow(row)
        self.table.blockSignals(False)

    def select_controller(self, results_dir):
        index = self.controller.findData(str(results_dir))
        if index >= 0:
            self.controller.setCurrentIndex(index)
            self.kind.setCurrentText("adapter")

    def _select(self):
        rows = {item.row() for item in self.table.selectedItems()}
        self.selected = self.evaluations[min(rows)] if rows else None
        if not self.selected:
            self.detail_label.setText("select an evaluation")
            self.detail.clear()
            return
        ev = self.selected
        m = ev.measurements
        self.detail_label.setText(f"{ev.name} · {ev.status}")
        lines = [f"controller: {ev.kind}  adapter sha256: {ev.adapter_sha256 or '–'}",
                 f"set: {ev.scenario_set}  mode: {ev.mode}  seed: {ev.contract.get('seed', '–')}  temperature: {ev.contract.get('temperature', 'config')}",
                 f"successes: {m.get('successes')}/{m.get('trials')}  arrived within 15 s: {m.get('arrived_within_15s')}  falls: {m.get('falls')}",
                 f"failure reasons: {m.get('failure_reasons')}",
                 f"mean time to arrival: {_f(m.get('mean_time_to_arrival_s'))} s  mean time to settle: {_f(m.get('mean_time_to_settle_s'))} s",
                 f"min pelvis height: {_f(m.get('min_pelvis_height_m'))} m  max planar speed: {_f(m.get('max_planar_speed_mps'))} m/s",
                 f"gate (90/100): {m.get('gate_passed_90_percent')}   run outcome: {ev.outcome.get('status')} exit {ev.outcome.get('process_exit_code')}",
                 f"results: {ev.output_dir}", f"evidence: {ev.evidence_dir}"]
        self.detail.setPlainText("\n".join(lines))
        self.video_button.setEnabled(bool(ev.media()))

    def _open_topdown(self):
        if self.selected:
            images = sorted(self.selected.output_dir.glob("topdown-*.png"))
            if images:
                open_path(images[0])

    def _open_video(self):
        if self.selected:
            media = self.selected.media()
            if media:
                open_path(media[0])

    def start(self):
        if self.jobs.active() or st.gpu_lock_held():
            QMessageBox.warning(self, "GPU busy", "Another studio GPU job is running. One heavy GPU job at a time.")
            return
        results_dir = self.controller.currentData()
        if not results_dir:
            QMessageBox.warning(self, "No controller", "No trained adapter is available.")
            return
        argv = [str(SCRIPTS / "run_milestone3_eval.sh"), self.kind.currentText(), self.scenario.currentText(), results_dir,
                "--seed", str(self.seed.value())]
        if self.label.text().strip():
            argv += ["--label", self.label.text().strip()]
        if self.record.text().strip():
            argv += ["--record", self.record.text().strip()]
        if self.temperature.text().strip():
            argv += ["--temperature", self.temperature.text().strip()]
        self.jobs.start(f"eval {self.kind.currentText()} {self.scenario.currentText()}", argv)
        QTimer.singleShot(3000, self.refresh)


def _f(value):
    return "–" if value is None else f"{float(value):.2f}"
