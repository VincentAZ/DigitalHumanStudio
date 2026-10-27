"""Live scene: direct the character in a running interactive Isaac worker."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from studio_app import SCRIPTS
from studio_app import state as st
from studio_app.jobs import JobCenter, docker_stop, open_path
from studio_app.plot import INK, INK_SOFT, STATUS

STATE_COLOURS = {"walking": "#1baf7a", "standing": "#2a78d6", "stopping": "#eda100", "fallen": "#d13438", "paused": "#8a8984"}


class RoomMap(QWidget):
    """Top-down room view; a click requests a destination in world coordinates."""
    destination_requested = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state: dict = {}
        self.trail: list[tuple[float, float, str]] = []
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def update_state(self, state: dict):
        self.state = state or {}
        xy = self.state.get("root_xy")
        if xy and not self.state.get("paused"):
            if not self.trail or (abs(self.trail[-1][0] - xy[0]) + abs(self.trail[-1][1] - xy[1])) > 0.01:
                self.trail.append((xy[0], xy[1], self.state.get("state", "")))
                del self.trail[:-6000]
        self.update()

    def clear_trail(self):
        self.trail.clear()
        self.update()

    def _geometry(self):
        half = float(self.state.get("room_half_size", 6.0))
        spawn = self.state.get("spawn_xy") or [0.0, 0.0]
        side = min(self.width(), self.height()) - 24
        scale = side / (2 * half + 1.0)
        centre = QPointF(self.width() / 2, self.height() / 2)
        return half, spawn, scale, centre

    def to_px(self, x: float, y: float) -> QPointF:
        half, spawn, scale, centre = self._geometry()
        return QPointF(centre.x() + (x - spawn[0]) * scale, centre.y() - (y - spawn[1]) * scale)

    def to_world(self, point: QPointF):
        half, spawn, scale, centre = self._geometry()
        return spawn[0] + (point.x() - centre.x()) / scale, spawn[1] - (point.y() - centre.y()) / scale

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fcfcfb"))
        half, spawn, scale, centre = self._geometry()
        painter.setPen(QPen(QColor("#e4e3df"), 1))
        for metre in range(-int(half), int(half) + 1):
            painter.drawLine(self.to_px(spawn[0] + metre, spawn[1] - half), self.to_px(spawn[0] + metre, spawn[1] + half))
            painter.drawLine(self.to_px(spawn[0] - half, spawn[1] + metre), self.to_px(spawn[0] + half, spawn[1] + metre))
        painter.setPen(QPen(QColor("#52514e"), 2))
        top_left = self.to_px(spawn[0] - half, spawn[1] + half)
        painter.drawRect(QRectF(top_left, QPointF(top_left.x() + 2 * half * scale, top_left.y() + 2 * half * scale)))
        for a, b in zip(self.trail[:-1], self.trail[1:]):
            painter.setPen(QPen(QColor(STATE_COLOURS.get(b[2], "#52514e")), 2))
            painter.drawLine(self.to_px(a[0], a[1]), self.to_px(b[0], b[1]))
        destination = self.state.get("destination")
        if destination:
            centre_px = self.to_px(*destination)
            radius = 0.3 * scale
            painter.setPen(QPen(QColor("#2a78d6"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre_px, radius, radius)
            painter.drawLine(QPointF(centre_px.x() - 6, centre_px.y()), QPointF(centre_px.x() + 6, centre_px.y()))
            painter.drawLine(QPointF(centre_px.x(), centre_px.y() - 6), QPointF(centre_px.x(), centre_px.y() + 6))
        spawn_px = self.to_px(*spawn)
        painter.setPen(QPen(QColor("#8a8984"), 1))
        painter.setBrush(QBrush(QColor("#fcfcfb")))
        painter.drawEllipse(spawn_px, 5, 5)
        xy = self.state.get("root_xy")
        if xy:
            yaw = float(self.state.get("yaw", 0.0))
            position = self.to_px(*xy)
            colour = QColor(STATE_COLOURS.get(self.state.get("state", ""), "#52514e"))
            size = max(0.25 * scale, 8)
            nose = QPointF(position.x() + math.cos(yaw) * size, position.y() - math.sin(yaw) * size)
            left = QPointF(position.x() + math.cos(yaw + 2.5) * size * 0.8, position.y() - math.sin(yaw + 2.5) * size * 0.8)
            right = QPointF(position.x() + math.cos(yaw - 2.5) * size * 0.8, position.y() - math.sin(yaw - 2.5) * size * 0.8)
            painter.setPen(QPen(QColor("#fcfcfb"), 2))
            painter.setBrush(QBrush(colour))
            painter.drawPolygon(QPolygonF([nose, left, right]))
        painter.setPen(INK_SOFT)
        painter.setFont(QFont(self.font().family(), 8))
        painter.drawText(QPointF(6, 14), f"Room ±{half:g} m around spawn · click to send the character there")
        legend_x = 6
        for name, colour in STATE_COLOURS.items():
            painter.setPen(QPen(QColor(colour), 4))
            painter.drawLine(QPointF(legend_x, self.height() - 8), QPointF(legend_x + 12, self.height() - 8))
            painter.setPen(INK_SOFT)
            painter.drawText(QPointF(legend_x + 16, self.height() - 4), name)
            legend_x += 30 + painter.fontMetrics().horizontalAdvance(name)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.state.get("spawn_xy"):
            x, y = self.to_world(event.position())
            self.destination_requested.emit(x, y)


class LiveView(QWidget):
    def __init__(self, jobs: JobCenter, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.session: dict | None = None
        self.state: dict = {}
        self._frame_mtime = 0.0
        self._state_mtime = 0.0
        self._status_lines = 0
        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(33)
        self.refresh_controllers()
        self._adopt_existing()

    # ---- layout -------------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        session_box = QGroupBox("Session")
        session_layout = QHBoxLayout(session_box)
        self.controller_combo = QComboBox()
        self.controller_combo.setMinimumWidth(320)
        self.preview_combo = QComboBox()
        self.preview_combo.addItems(["640x480", "960x540", "1280x720"])
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("optional label")
        self.start_button = QPushButton("Start live session")
        self.start_button.clicked.connect(self.start_session)
        self.quit_button = QPushButton("End session")
        self.quit_button.setToolTip("Sends quit: the worker finishes recording, cleans up and the launcher records evidence")
        self.quit_button.clicked.connect(lambda: self.send({"cmd": "quit"}))
        self.force_button = QPushButton("Force stop")
        self.force_button.setToolTip("docker stop of the worker container; the launcher records it as a failed session")
        self.force_button.clicked.connect(self.force_stop)
        self.session_label = QLabel("no live session")
        for widget in (QLabel("Controller"), self.controller_combo, QLabel("Preview"), self.preview_combo, self.label_edit,
                       self.start_button, self.quit_button, self.force_button):
            session_layout.addWidget(widget)
        session_layout.addStretch(1)
        root.addWidget(session_box)
        root.addWidget(self.session_label)

        middle = QHBoxLayout()
        self.preview = QLabel("preview appears here when a session is running")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(480, 360)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet("background: #1a1a19; color: #c3c2b7;")
        middle.addWidget(self.preview, 3)
        self.map = RoomMap()
        self.map.destination_requested.connect(self.request_destination)
        middle.addWidget(self.map, 2)
        root.addLayout(middle, 1)

        bottom = QHBoxLayout()
        controls = QGroupBox("Controls")
        grid = QGridLayout(controls)
        self.stop_button = QPushButton("Stop walking")
        self.stop_button.clicked.connect(lambda: self.send({"cmd": "stop"}))
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.reset_button = QPushButton("Reset")
        self.reset_button.setToolTip("Explicit return to the session spawn point (never automatic)")
        self.reset_button.clicked.connect(self.reset)
        self.record_button = QPushButton("Start recording segment")
        self.record_button.clicked.connect(self.toggle_record)
        self.push_x = QDoubleSpinBox()
        self.push_x.setRange(-6.0, 6.0)
        self.push_x.setValue(2.0)
        self.push_x.setSuffix(" m/s x")
        self.push_y = QDoubleSpinBox()
        self.push_y.setRange(-6.0, 6.0)
        self.push_y.setSuffix(" m/s y")
        self.push_button = QPushButton("Push")
        self.push_button.clicked.connect(lambda: self.send({"cmd": "push", "vx": self.push_x.value(), "vy": self.push_y.value()}))
        self.local_x = QDoubleSpinBox()
        self.local_x.setRange(-12, 12)
        self.local_x.setValue(3.0)
        self.local_x.setSuffix(" m ahead")
        self.local_y = QDoubleSpinBox()
        self.local_y.setRange(-12, 12)
        self.local_y.setSuffix(" m left")
        self.local_button = QPushButton("Walk relative")
        self.local_button.clicked.connect(lambda: self.send({"cmd": "destination", "x": self.local_x.value(), "y": self.local_y.value(), "frame": "local"}))
        grid.addWidget(self.stop_button, 0, 0)
        grid.addWidget(self.pause_button, 0, 1)
        grid.addWidget(self.reset_button, 0, 2)
        grid.addWidget(self.record_button, 0, 3)
        grid.addWidget(self.local_x, 1, 0)
        grid.addWidget(self.local_y, 1, 1)
        grid.addWidget(self.local_button, 1, 2)
        grid.addWidget(self.push_x, 2, 0)
        grid.addWidget(self.push_y, 2, 1)
        grid.addWidget(self.push_button, 2, 2)
        bottom.addWidget(controls, 2)

        status = QGroupBox("Character")
        form = QFormLayout(status)
        self.status_labels = {}
        for key, title in (("state", "State"), ("sim_time", "Simulated time"), ("speed", "Pelvis speed"),
                           ("distance", "Distance to target"), ("rate", "Control steps / wall s"),
                           ("resets", "Resets"), ("recording", "Recording")):
            label = QLabel("–")
            self.status_labels[key] = label
            form.addRow(title, label)
        bottom.addWidget(status, 1)

        log_box = QGroupBox("Command acknowledgements")
        log_layout = QVBoxLayout(log_box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        log_layout.addWidget(self.log)
        bottom.addWidget(log_box, 2)
        root.addLayout(bottom)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        for widget in (self.stop_button, self.pause_button, self.reset_button, self.record_button, self.push_button,
                       self.local_button, self.quit_button, self.force_button):
            widget.setEnabled(enabled)
        self.start_button.setEnabled(not enabled)

    # ---- controllers ----------------------------------------------------------------------
    def refresh_controllers(self):
        current = self.controller_combo.currentData()
        self.controller_combo.clear()
        self.controller_combo.addItem("Tracker-driven walker  (Milestone 1 tracker + licensed clips, no training)", "tracker")
        for run in st.list_controllers():
            title = f"{run.experiment}  ({run.created}, {run.epochs} epochs)"
            self.controller_combo.addItem(title, str(run.results_dir))
        if current is not None:
            index = self.controller_combo.findData(current)
            if index >= 0:
                self.controller_combo.setCurrentIndex(index)

    def select_controller(self, results_dir: Path):
        index = self.controller_combo.findData(str(results_dir))
        if index >= 0:
            self.controller_combo.setCurrentIndex(index)

    # ---- session lifecycle ----------------------------------------------------------------
    def _adopt_existing(self):
        pointer = st.current_live_pointer()
        if pointer and not pointer["finished"]:
            self._attach(pointer)

    def _attach(self, pointer: dict):
        self.session = pointer
        self.map.clear_trail()
        self._frame_mtime = self._state_mtime = 0.0
        self._status_lines = 0
        self.log.clear()
        self._set_controls_enabled(True)
        self.session_label.setText(f"Session {Path(pointer['output']).name} · container {pointer['container']} · starting Isaac…")

    def start_session(self):
        results_dir = self.controller_combo.currentData()
        if not results_dir:
            QMessageBox.warning(self, "No controller", "Train a walking adapter first (Training view).")
            return
        if self.jobs.active() or st.gpu_lock_held():
            QMessageBox.warning(self, "GPU busy", "Another studio GPU job is running. One heavy GPU job at a time.")
            return
        argv = [str(SCRIPTS / "run_milestone3_live.sh"), results_dir, "--interactive", "--preview", self.preview_combo.currentText()]
        label = self.label_edit.text().strip()
        if label:
            argv += ["--label", label]
        before = st.current_live_pointer()
        before_stamp = before.get("started_utc") if before else None
        self.jobs.start("live session", argv)
        self.session = None
        self.session_label.setText("launching live session…")
        self._pending_stamp = before_stamp
        self.start_button.setEnabled(False)
        QTimer.singleShot(500, self._wait_pointer)

    def _wait_pointer(self):
        pointer = st.current_live_pointer()
        if pointer and pointer.get("started_utc") != getattr(self, "_pending_stamp", None) and not pointer["finished"]:
            self._attach(pointer)
            return
        if not self.jobs.active():
            self.session_label.setText("launcher exited before a session started; see the job log")
            self.start_button.setEnabled(True)
            return
        QTimer.singleShot(500, self._wait_pointer)

    def force_stop(self):
        if not self.session:
            return
        if QMessageBox.question(self, "Force stop", "Stop the worker container now? The launcher will record a failed session.") != QMessageBox.StandardButton.Yes:
            return
        self.log.appendPlainText(docker_stop(self.session["container"]) or "stop requested")

    def _session_ended(self):
        self._set_controls_enabled(False)
        if self.session:
            outcome = st.read_json(Path(self.session["evidence"]) / "outcome.json", {}) or {}
            self.session_label.setText(f"Session {Path(self.session['output']).name} ended: {outcome.get('status', 'unknown')} "
                                       f"(exit {outcome.get('process_exit_code', '?')}, {outcome.get('steps', '?')} steps). "
                                       f"Recording: {Path(self.session['output']) / 'performance.mp4'}")
        self.session = None

    # ---- commands -------------------------------------------------------------------------
    def send(self, command: dict):
        if not self.session:
            return
        command = dict(command)
        command["issued_wall_time"] = time.time()
        try:
            with (Path(self.session["output"]) / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps(command) + "\n")
                stream.flush()
        except OSError as error:
            self.log.appendPlainText(f"could not write command: {error}")

    def request_destination(self, x: float, y: float):
        self.send({"cmd": "destination", "x": round(x, 3), "y": round(y, 3), "frame": "world"})

    def toggle_pause(self):
        self.send({"cmd": "resume"} if self.state.get("paused") else {"cmd": "pause"})

    def toggle_record(self):
        self.send({"cmd": "record", "action": "stop" if self.state.get("recording") else "start",
                   "name": f"segment-{int(time.time())}"})

    def reset(self):
        self.send({"cmd": "reset"})

    # ---- polling --------------------------------------------------------------------------
    def _poll(self):
        if not self.session:
            # Attach to a session started outside this window (or after a failed start) once per second.
            self._pointer_checks = getattr(self, "_pointer_checks", 0) + 1
            if self._pointer_checks % 30 == 0 and self.start_button.isEnabled():
                self._adopt_existing()
            return
        output = Path(self.session["output"])
        live = output / "live"
        try:
            state_mtime = (live / "state.json").stat().st_mtime
        except OSError:
            state_mtime = 0.0
        if state_mtime and state_mtime != self._state_mtime:
            self._state_mtime = state_mtime
            state = st.read_json(live / "state.json")
            if state:
                self.state = state
                self.map.update_state(state)
                self._render_status(state)
        try:
            frame_mtime = (live / "frame.jpg").stat().st_mtime
        except OSError:
            frame_mtime = 0.0
        if frame_mtime and frame_mtime != self._frame_mtime:
            pixmap = QPixmap(str(live / "frame.jpg"))
            if not pixmap.isNull():
                self._frame_mtime = frame_mtime
                self.preview.setPixmap(pixmap.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))
        records = st.read_jsonl(output / "status.jsonl")
        if len(records) > self._status_lines:
            for record in records[self._status_lines:]:
                self.log.appendPlainText(self._format_status(record))
            self._status_lines = len(records)
        if st.job_finished(Path(self.session["evidence"])):
            self._session_ended()

    def _render_status(self, state: dict):
        colour = STATE_COLOURS.get(state.get("state", ""), "#52514e")
        phase = f" · reference: {state['phase']}" if state.get("phase") else ""
        self.status_labels["state"].setText(f"<span style='color:{colour}; font-weight:600'>{state.get('state')}</span>"
                                            + (" (fallen: reset required)" if state.get("fallen") else "") + phase)
        self.status_labels["sim_time"].setText(f"{state.get('sim_time', 0):.2f} s · step {state.get('step', 0)}")
        self.status_labels["speed"].setText(f"{state.get('speed', 0):.3f} m/s")
        self.status_labels["distance"].setText(f"{state.get('distance', 0):.2f} m")
        rate = state.get("steps_per_wall_second")
        self.status_labels["rate"].setText("–" if rate is None else f"{rate:.1f} (control runs at 30 Hz simulated)")
        self.status_labels["resets"].setText(str(state.get("resets", 0)))
        self.status_labels["recording"].setText(state.get("recording") or f"idle ({state.get('recording_segments', 0)} segments saved)")
        self.pause_button.setText("Resume" if state.get("paused") else "Pause")
        self.record_button.setText("Stop recording segment" if state.get("recording") else "Start recording segment")
        self.session_label.setText(f"Session {Path(self.session['output']).name} · container {self.session['container']} · "
                                   f"preview {'x'.join(str(v) for v in state.get('preview_size', []))} · {state.get('controller', 'adapter')} {state.get('adapter_sha256', '')[:12]}")

    @staticmethod
    def _format_status(record: dict) -> str:
        event = record.get("event")
        when = f"t={record.get('sim_time', 0):.2f}s"
        if event == "command":
            command = record.get("command", {})
            latency = record.get("ack_latency_ms", 0.0)
            return f"{when} {command.get('cmd')} → {record.get('result')} ({latency:.1f} ms)"
        return f"{when} {event} {json.dumps({k: v for k, v in record.items() if k not in ('event', 'sim_time', 'step', 'wall_time', 'state')})}"
