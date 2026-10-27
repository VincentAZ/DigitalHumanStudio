"""Assistant dock: chat with the director's assistant from the control center."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from studio_app import ROOT
from studio_assistant import TRANSCRIPTS
from studio_assistant.providers import PROVIDERS, key_status, load_config, make_assistant, provider_settings, save_config


class TurnWorker(QThread):
    event = Signal(str, dict)

    def __init__(self, assistant, text: str, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.text = text

    def run(self):
        try:
            self.assistant.run_turn(self.text, lambda kind, payload: self.event.emit(kind, payload))
        except Exception as error:
            self.event.emit("error", {"message": str(error)})
            self.event.emit("done", {"text": ""})


class KeyDialog(QDialog):
    def __init__(self, provider: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{PROVIDERS[provider]['title']} settings")
        settings = provider_settings(provider)
        form = QFormLayout(self)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("API key (stored in ~/.config/digital-human-studio/providers.json, mode 600)")
        self.model = QLineEdit(settings.get("model", ""))
        self.base_url = QLineEdit(settings.get("base_url", ""))
        form.addRow("API key", self.key)
        form.addRow("Model", self.model)
        if settings["kind"] != "agent_sdk":
            form.addRow("Base URL", self.base_url)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.provider = provider

    def save(self):
        config = load_config()
        entry = config.get(self.provider, {})
        if self.key.text().strip():
            entry["api_key"] = self.key.text().strip()
        entry["model"] = self.model.text().strip()
        if self.base_url.text().strip():
            entry["base_url"] = self.base_url.text().strip()
        config[self.provider] = entry
        save_config(config)


class AssistantPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.assistant = None
        self.worker = None
        self.transcript_path = None
        self._build()
        self._provider_changed()

    def _build(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.provider = QComboBox()
        for name, meta in PROVIDERS.items():
            self.provider.addItem(meta["title"], name)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.status = QLabel("")
        self.settings_button = QPushButton("Settings…")
        self.settings_button.clicked.connect(self._settings)
        self.new_button = QPushButton("New conversation")
        self.new_button.clicked.connect(self._reset)
        for widget in (QLabel("Assistant"), self.provider, self.status, self.settings_button, self.new_button):
            top.addWidget(widget)
        top.addStretch(1)
        root.addLayout(top)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        root.addWidget(self.view, 1)
        bottom = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Tell the assistant what the character should do, e.g. “load the work cell and walk to the machine”. Ctrl+Enter sends.")
        self.input.setMaximumHeight(70)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        bottom.addWidget(self.input, 1)
        bottom.addWidget(self.send_button)
        root.addLayout(bottom)
        self.input.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.input and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.send()
            return True
        return super().eventFilter(obj, event)

    def _provider_changed(self):
        name = self.provider.currentData()
        self.status.setText(f"{key_status(name)} · model {provider_settings(name).get('model') or 'default'}")
        self._reset()

    def _settings(self):
        dialog = KeyDialog(self.provider.currentData(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save()
            self._provider_changed()

    def _reset(self):
        if self.assistant is not None and hasattr(self.assistant, "close"):
            try:
                self.assistant.close()
            except Exception:
                pass
        self.assistant = None
        self.transcript_path = None
        self.view.clear()

    def _ensure_assistant(self) -> bool:
        if self.assistant is not None:
            return True
        name = self.provider.currentData()
        try:
            self.assistant = make_assistant(name)
        except Exception as error:
            QMessageBox.warning(self, "Assistant unavailable", str(error))
            return False
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = TRANSCRIPTS / f"{stamp}-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        self.transcript_path = folder / "transcript.jsonl"
        return True

    def _log(self, record: dict):
        if self.transcript_path:
            with self.transcript_path.open("a") as stream:
                stream.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), **record}) + "\n")

    def send(self):
        text = self.input.toPlainText().strip()
        if not text or (self.worker is not None and self.worker.isRunning()):
            return
        if not self._ensure_assistant():
            return
        self.input.clear()
        self.view.append(f"<p><b>You:</b> {text}</p>")
        self.view.append("<p><b>Assistant:</b> ")
        self._log({"kind": "user", "text": text})
        self.send_button.setEnabled(False)
        self.worker = TurnWorker(self.assistant, text, self)
        self.worker.event.connect(self._event)
        self.worker.start()

    def _event(self, kind: str, payload: dict):
        self._log({"kind": kind, **payload})
        cursor = self.view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if kind == "text":
            cursor.insertText(payload["delta"])
        elif kind == "tool_call":
            cursor.insertHtml(f"<br><span style='color:#52514e'>→ {payload['name']}({json.dumps(payload['arguments'])})</span><br>")
        elif kind == "tool_result":
            summary = json.dumps(payload["result"])
            cursor.insertHtml(f"<span style='color:#52514e'>← {summary[:240]}{'…' if len(summary) > 240 else ''}</span><br>")
        elif kind == "error":
            cursor.insertHtml(f"<br><span style='color:#d13438'>error: {payload['message']}</span><br>")
        elif kind == "done":
            cursor.insertHtml("</p>")
            self.send_button.setEnabled(True)
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()
