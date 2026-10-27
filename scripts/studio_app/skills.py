"""Skills view: trained controllers, their training outcome and best evaluation scores."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from studio_app import state as st
from studio_app.jobs import open_path

COLUMNS = ["controller", "trained", "epochs", "episode reward", "fall %", "flat /100", "redirect /100", "push /100", "gates", "adapter sha256"]


class SkillsView(QWidget):
    use_in_live = Signal(object)
    evaluate = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controllers: list[st.TrainingRun] = []
        self.selected: st.TrainingRun | None = None
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10000)

    def _build(self):
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Walking adapters trained on the frozen GPC movement prior (skill: destination walking). "
                              "Acceptance needs 90/100 on flat and redirect; no controller has met it yet."))
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._select)
        root.addWidget(self.table, 2)
        actions = QHBoxLayout()
        self.live_button = QPushButton("Direct in live scene")
        self.live_button.clicked.connect(lambda: self.selected and self.use_in_live.emit(self.selected))
        self.eval_button = QPushButton("Evaluate")
        self.eval_button.clicked.connect(lambda: self.selected and self.evaluate.emit(self.selected))
        self.folder_button = QPushButton("Open checkpoint folder")
        self.folder_button.clicked.connect(lambda: self.selected and open_path(self.selected.results_dir))
        for widget in (self.live_button, self.eval_button, self.folder_button):
            actions.addWidget(widget)
        actions.addStretch(1)
        root.addLayout(actions)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        root.addWidget(self.detail, 1)

    def refresh(self):
        selected_name = self.selected.name if self.selected else None
        self.controllers = sorted(st.list_controllers(), key=lambda run: run.stamp, reverse=True)
        evaluations = st.list_evaluations()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.controllers))
        for row, run in enumerate(self.controllers):
            scores = st.best_scores(evaluations, run.sha256)
            last = run.last

            def score(name):
                ev = scores.get(name)
                return "–" if ev is None else str(ev.successes)
            gates = all(scores.get(name) and scores[name].successes >= 90 for name in ("flat", "redirect"))
            values = [run.experiment, run.created, run.epochs, _fmt(last.get("info/episode_reward")),
                      _fmt((last.get("env/termination/fall_mean") or 0) * 100, 1), score("flat"), score("redirect"), score("push"),
                      "met" if gates else "not met", run.sha256[:16] or "–"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 8:
                    item.setForeground(Qt.GlobalColor.darkGreen if gates else Qt.GlobalColor.darkRed)
                self.table.setItem(row, column, item)
            if run.name == selected_name:
                self.table.selectRow(row)
        self.table.blockSignals(False)

    def _select(self):
        rows = {item.row() for item in self.table.selectedItems()}
        self.selected = self.controllers[min(rows)] if rows else None
        if not self.selected:
            self.detail.clear()
            return
        run = self.selected
        lines = [f"experiment: {run.experiment}   stage: {run.stage}   status: {run.status}",
                 f"checkpoint: {run.checkpoint}", f"adapter sha256: {run.sha256 or 'not recorded'}",
                 f"warm start: {run.contract.get('warm_start_checkpoint') or 'none'}",
                 f"environments: {run.contract.get('num_envs')}  batch: {run.contract.get('batch_size')}  cap: {run.contract.get('wall_clock_seconds')} s  seed: {run.contract.get('seed')}",
                 f"epochs: {run.epochs}  elapsed: {(run.last.get('elapsed_seconds') or 0) / 60:.0f} min  steps: {run.last.get('step_count')}",
                 f"training outcome: {run.outcome}", f"evidence: {run.evidence_dir}"]
        self.detail.setPlainText("\n".join(lines))


def _fmt(value, digits=2):
    return "–" if value is None else f"{float(value):.{digits}f}"
