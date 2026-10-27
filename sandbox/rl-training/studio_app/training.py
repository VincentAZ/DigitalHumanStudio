"""Training view: start bounded jobs, follow progress, stop cleanly, cancel."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from studio_app import SCRIPTS
from studio_app import state as st
from studio_app.jobs import JobCenter, docker_stop, open_path
from studio_app.plot import LinePlot

COLUMNS = ["experiment", "stage", "status", "epochs", "minutes", "episode reward", "standing", "fall %", "steps/s", "GPU GiB", "started"]


class TrainingView(QWidget):
    def __init__(self, jobs: JobCenter, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.runs: list[st.TrainingRun] = []
        self.selected: st.TrainingRun | None = None
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

    def _build(self):
        root = QVBoxLayout(self)
        launch = QGroupBox("Start a bounded training job (recorded by scripts/run_milestone3_train.sh)")
        form = QFormLayout(launch)
        self.stage = QComboBox()
        self.stage.addItems(["rlft", "sft"])
        self.stage.currentTextChanged.connect(self._stage_defaults)
        self.seed = QSpinBox()
        self.seed.setRange(0, 9999)
        self.envs = QSpinBox()
        self.envs.setRange(64, 8192)
        self.envs.setValue(2048)
        self.batch = QSpinBox()
        self.batch.setRange(64, 8192)
        self.batch.setValue(2048)
        self.minutes = QSpinBox()
        self.minutes.setRange(5, 480)
        self.minutes.setValue(240)
        self.minutes.setSuffix(" min (plan cap 8 h)")
        self.experiment = QLineEdit("m3_rlft_walk_seed0_attempt4")
        self.warm = QComboBox()
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("extra train_agent arguments (optional)")
        self.start_button = QPushButton("Start training")
        self.start_button.clicked.connect(self.start)
        form.addRow("Stage", self.stage)
        form.addRow("Seed", self.seed)
        form.addRow("Environments", self.envs)
        form.addRow("Batch size", self.batch)
        form.addRow("Wall-clock cap", self.minutes)
        form.addRow("Experiment name", self.experiment)
        form.addRow("Warm start", self.warm)
        form.addRow("Extra arguments", self.extra)
        form.addRow(self.start_button)
        root.addWidget(launch)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._select)
        splitter.addWidget(self.table)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        actions = QHBoxLayout()
        self.detail_label = QLabel("select a run")
        self.stop_button = QPushButton("Stop after this epoch")
        self.stop_button.setToolTip("Writes STOP_REQUESTED next to metrics.jsonl; the worker saves a final checkpoint and exits 0")
        self.stop_button.clicked.connect(self.request_stop)
        self.cancel_button = QPushButton("Cancel now")
        self.cancel_button.setToolTip("docker stop; the launcher records a failed run and keeps the container")
        self.cancel_button.clicked.connect(self.cancel)
        self.open_button = QPushButton("Open results folder")
        self.open_button.clicked.connect(lambda: self.selected and open_path(self.selected.output_dir))
        self.evidence_button = QPushButton("Open evidence folder")
        self.evidence_button.clicked.connect(lambda: self.selected and open_path(self.selected.evidence_dir))
        for widget in (self.detail_label, self.stop_button, self.cancel_button, self.open_button, self.evidence_button):
            actions.addWidget(widget)
        actions.addStretch(1)
        detail_layout.addLayout(actions)
        plots = QHBoxLayout()
        self.reward_plot = LinePlot("Episode reward")
        self.components_plot = LinePlot("Reward components (mean, 0–1)")
        self.fall_plot = LinePlot("Fall rate (%) and entropy (nats)")
        for plot in (self.reward_plot, self.components_plot, self.fall_plot):
            plots.addWidget(plot)
        detail_layout.addLayout(plots)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        detail_layout.addWidget(self.log)
        splitter.addWidget(detail)
        splitter.setSizes([220, 500])
        root.addWidget(splitter, 1)

    def _stage_defaults(self, stage: str):
        if stage == "sft":
            self.envs.setValue(1024)
            self.batch.setValue(1024)
            self.minutes.setValue(75)
            self.experiment.setText("m3_sft_walk")
        else:
            self.envs.setValue(2048)
            self.batch.setValue(2048)
            self.minutes.setValue(240)
            self.experiment.setText("m3_rlft_walk_seed0_attempt4")

    # ---- data -----------------------------------------------------------------------------
    def refresh(self):
        selected_name = self.selected.name if self.selected else None
        self.runs = sorted(st.list_training_runs(), key=lambda run: run.stamp, reverse=True)
        current_warm = self.warm.currentData()
        self.warm.blockSignals(True)
        self.warm.clear()
        self.warm.addItem("none (fresh adapter)", "")
        for run in self.runs:
            if run.last_ckpt.exists():
                self.warm.addItem(f"{run.experiment} ({run.created})", str(run.last_ckpt))
        if current_warm:
            index = self.warm.findData(current_warm)
            if index >= 0:
                self.warm.setCurrentIndex(index)
        self.warm.blockSignals(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.runs))
        for row, run in enumerate(self.runs):
            last = run.last
            values = [run.experiment, run.stage, run.status, run.epochs,
                      f"{(last.get('elapsed_seconds') or 0) / 60:.0f}",
                      _fmt(last.get("info/episode_reward")), _fmt(last.get("env/raw_r/standing_mean")),
                      _fmt((last.get("env/termination/fall_mean") or 0) * 100, 1), _fmt(last.get("times/fps_last_epoch"), 0),
                      _fmt(last.get("max_gpu_memory_gib"), 1), run.created]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 2:
                    item.setForeground(Qt.GlobalColor.darkGreen if value == "passed" else Qt.GlobalColor.darkRed if value == "failed" else Qt.GlobalColor.darkBlue)
                self.table.setItem(row, column, item)
            if run.name == selected_name:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        if self.selected:
            match = [run for run in self.runs if run.name == self.selected.name]
            self.selected = match[0] if match else None
            self._render_selected()

    def _select(self):
        rows = {item.row() for item in self.table.selectedItems()}
        self.selected = self.runs[min(rows)] if rows else None
        self._render_selected()

    def _render_selected(self):
        run = self.selected
        enabled = bool(run and run.running)
        self.stop_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
        if not run:
            self.detail_label.setText("select a run")
            return
        outcome = run.outcome
        self.detail_label.setText(f"{run.name} · {run.status} · exit {outcome.get('process_exit_code', '–')} · "
                                  f"warm start: {Path(run.contract.get('warm_start_checkpoint') or '').name or 'none'} · "
                                  f"cap {int(run.contract.get('wall_clock_seconds') or 0) // 60} min")
        metrics = st.read_jsonl(run.metrics_path)
        epochs = [m.get("epoch", i) for i, m in enumerate(metrics)]

        def series(key, scale=1.0):
            return [((m.get(key) or 0.0) * scale) for m in metrics]
        if run.stage == "sft":
            self.reward_plot.set_series([("token loss", epochs, series("sft/loss"))])
            self.components_plot.set_series([("token accuracy", epochs, series("sft/accuracy"))])
            self.fall_plot.set_series([])
        else:
            self.reward_plot.set_series([("episode reward", epochs, series("info/episode_reward"))])
            self.components_plot.set_series([("standing", epochs, series("env/raw_r/standing_mean")),
                                             ("progress", epochs, series("env/raw_r/progress_mean")),
                                             ("target", epochs, series("env/raw_r/target_mean")),
                                             ("upright", epochs, series("env/raw_r/upright_mean"))])
            self.fall_plot.set_series([("fall %", epochs, series("env/termination/fall_mean", 100.0)),
                                       ("entropy", epochs, series("actor/entropy"))])
        try:
            lines = (run.evidence_dir / "session.log").read_text(errors="replace").splitlines()[-80:]
        except OSError:
            lines = ["(no session log yet)"]
        self.log.setPlainText("\n".join(lines))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    # ---- actions --------------------------------------------------------------------------
    def start(self):
        if self.jobs.active() or st.gpu_lock_held():
            QMessageBox.warning(self, "GPU busy", "Another studio GPU job is running. One heavy GPU job at a time.")
            return
        name = self.experiment.text().strip()
        if not name or any(run.experiment == name for run in self.runs):
            QMessageBox.warning(self, "Experiment name", "Choose a new, non-empty experiment name.")
            return
        argv = [str(SCRIPTS / "run_milestone3_train.sh"), self.stage.currentText(), str(self.seed.value()), str(self.envs.value()),
                str(self.batch.value()), str(self.minutes.value() * 60), name]
        if self.warm.currentData():
            argv += ["--warm-start", self.warm.currentData()]
        extra = self.extra.text().split()
        if extra:
            argv += ["--", *extra]
        self.jobs.start(f"train {name}", argv)
        QTimer.singleShot(3000, self.refresh)

    def request_stop(self):
        if self.selected and self.selected.running:
            (self.selected.output_dir / "STOP_REQUESTED").touch()
            self.log.appendPlainText("STOP_REQUESTED written; the worker stops after the current epoch and saves last.ckpt.")

    def cancel(self):
        if not (self.selected and self.selected.running):
            return
        if QMessageBox.question(self, "Cancel training", "Stop the container now? The run is recorded as failed and its container kept.") != QMessageBox.StandardButton.Yes:
            return
        containers = [line.split("\t")[0] for line in st.running_containers() if line.startswith("studio-m3-train-")]
        for container in containers:
            self.log.appendPlainText(docker_stop(container) or f"stop requested for {container}")
        if not containers:
            self.log.appendPlainText("no running training container found")


def _fmt(value, digits=3):
    if value is None:
        return "–"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
