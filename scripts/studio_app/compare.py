"""Compare view: the same route through a scene with both locomotion modes, side by side."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from studio_app import ARTIFACTS, CONFIG, SCRIPTS
from studio_app import state as st
from studio_app.jobs import JobCenter, open_path

ROWS = [("legs", "route legs"), ("arrived", "legs arrived (within 0.3 m)"), ("held_2s", "legs held 2 s below 0.15 m/s"),
        ("mean_arrival_s", "mean time to arrival (s)"), ("median_post_arrival_speed", "median post-arrival speed (m/s)"),
        ("falls", "falls"), ("resets", "resets"), ("steps", "control steps")]


class CompareView(QWidget):
    def __init__(self, jobs: JobCenter, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.runs: list[Path] = []
        self.selected: Path | None = None
        self._build()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

    def _build(self):
        root = QVBoxLayout(self)
        launch = QGroupBox("Run the same route with both locomotion modes (scripts/run_milestone3_compare.sh; two GPU sessions in turn)")
        form = QFormLayout(launch)
        self.scene = QComboBox()
        for scene in sorted((CONFIG / "scenes").glob("*.json")):
            meta = st.read_json(scene, {}) or {}
            self.scene.addItem(f"{meta.get('name', scene.stem)}: {meta.get('description', '')[:70]}", scene.stem)
        self.adapter = QComboBox()
        self.label = QLineEdit()
        self.label.setPlaceholderText("optional label")
        self.start_button = QPushButton("Start comparison")
        self.start_button.clicked.connect(self.start)
        form.addRow("Scene", self.scene)
        form.addRow("Learned adapter", self.adapter)
        form.addRow("Label", self.label)
        form.addRow(self.start_button)
        root.addWidget(launch)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.runs_combo = QComboBox()
        self.runs_combo.currentIndexChanged.connect(self._select)
        left_layout.addWidget(QLabel("Recorded comparisons"))
        left_layout.addWidget(self.runs_combo)
        self.table = QTableWidget(len(ROWS), 2)
        self.table.setHorizontalHeaderLabels(["tracker-driven walker", "learned adapter"])
        self.table.setVerticalHeaderLabels([title for _, title in ROWS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left_layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.video_button = QPushButton("Open side-by-side video")
        self.video_button.clicked.connect(lambda: self.selected and open_path(self.selected / "side-by-side.mp4"))
        self.folder_button = QPushButton("Open comparison folder")
        self.folder_button.clicked.connect(lambda: self.selected and open_path(self.selected))
        actions.addWidget(self.video_button)
        actions.addWidget(self.folder_button)
        actions.addStretch(1)
        left_layout.addLayout(actions)
        self.note = QLabel("Metrics use the acceptance wording (0.3 m arrival, 2 s below 0.15 m/s). Two scripted sessions, not the 100-trial sets.")
        self.note.setWordWrap(True)
        left_layout.addWidget(self.note)
        splitter.addWidget(left)
        self.plots = QLabel("top-down plots appear here")
        self.plots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plots.setMinimumWidth(520)
        splitter.addWidget(self.plots)
        splitter.setSizes([560, 900])
        root.addWidget(splitter, 1)

    def refresh(self):
        controllers = [run for run in st.list_controllers() if run.stage == "rlft"]
        current = self.adapter.currentData()
        self.adapter.blockSignals(True)
        self.adapter.clear()
        for run in controllers:
            self.adapter.addItem(f"{run.experiment} ({run.created})", str(run.results_dir))
        if current:
            index = self.adapter.findData(current)
            if index >= 0:
                self.adapter.setCurrentIndex(index)
        self.adapter.blockSignals(False)
        runs = sorted((p for p in ARTIFACTS.glob("compare-*") if (p / "comparison.json").exists()), key=lambda p: p.name, reverse=True)
        if [p.name for p in runs] != [p.name for p in self.runs]:
            self.runs = runs
            selected = self.selected
            self.runs_combo.blockSignals(True)
            self.runs_combo.clear()
            for run in runs:
                self.runs_combo.addItem(run.name, str(run))
            if selected is not None:
                index = self.runs_combo.findData(str(selected))
                if index >= 0:
                    self.runs_combo.setCurrentIndex(index)
            self.runs_combo.blockSignals(False)
            self._select()

    def _select(self):
        data = self.runs_combo.currentData()
        self.selected = Path(data) if data else None
        if not self.selected:
            self.table.clearContents()
            self.plots.setText("no comparison recorded yet")
            return
        result = st.read_json(self.selected / "comparison.json", {}) or {}
        sides = result.get("sides", {})
        for row, (key, _) in enumerate(ROWS):
            for column, side in enumerate(("left", "right")):
                value = sides.get(side, {}).get("aggregate", {}).get(key)
                self.table.setItem(row, column, QTableWidgetItem("–" if value is None else str(value)))
        pixmap = QPixmap(str(self.selected / "topdowns.png"))
        if not pixmap.isNull():
            self.plots.setPixmap(pixmap.scaled(self.plots.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.video_button.setEnabled((self.selected / "side-by-side.mp4").exists())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._select()

    def start(self):
        if self.jobs.active() or st.gpu_lock_held():
            QMessageBox.warning(self, "GPU busy", "Another studio GPU job is running. End the live session first.")
            return
        if not self.adapter.currentData():
            QMessageBox.warning(self, "No adapter", "No trained walking adapter is available to compare against.")
            return
        argv = [str(SCRIPTS / "run_milestone3_compare.sh"), self.scene.currentData(), "--adapter", self.adapter.currentData()]
        if self.label.text().strip():
            argv += ["--label", self.label.text().strip()]
        self.jobs.start(f"compare {self.scene.currentData()}", argv)
