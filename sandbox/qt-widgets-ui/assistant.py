"""Assistant dock: chat with the director's assistant from the control center."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget)

from studio_app import ROOT
from studio_assistant import TRANSCRIPTS
from studio_assistant.tools import CANCEL
from studio_assistant.providers import PROVIDERS, THINKING_LEVELS, key_status, list_models, load_config, make_assistant, provider_settings, save_config


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
        self.provider = provider
        self.setWindowTitle(f"{PROVIDERS[provider]['title']} settings")
        self.setMinimumWidth(640)
        settings = provider_settings(provider)
        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        stored = "a key is stored" if (load_config().get(provider, {}).get("api_key")) else ("key from the environment" if settings.get("api_key") else "no key yet")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(f"{stored}; paste a new key to replace it")
        self.show_key = QCheckBox("show")
        self.show_key.toggled.connect(lambda on: self.key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(self.show_key)
        self.model = QComboBox()
        self.model.setEditable(True)
        for model in settings.get("models", []):
            self.model.addItem(model)
        self.model.setCurrentText(settings.get("model", ""))
        self.fetch_button = QPushButton("Fetch models")
        self.fetch_button.setToolTip("Ask the provider for its model list (uses the key above or the stored one)")
        self.fetch_button.clicked.connect(self._fetch)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model, 1)
        model_row.addWidget(self.fetch_button)
        self.thinking = QComboBox()
        self.thinking.addItems(THINKING_LEVELS)
        self.thinking.setCurrentText(settings.get("thinking", "default"))
        self.thinking.setToolTip("Reasoning effort: passed as reasoning_effort (OpenAI, Gemini, xAI), reasoning.effort (OpenRouter) or the Agent SDK's effort setting")
        self.base_url = QLineEdit(settings.get("base_url", ""))
        form.addRow("API key", key_row)
        form.addRow("Model", model_row)
        form.addRow("Thinking", self.thinking)
        if settings["kind"] != "agent_sdk":
            form.addRow("Base URL", self.base_url)
        note = QLabel("Stored in ~/.config/digital-human-studio/providers.json (mode 600); never in the project. "
                      + ("Claude needs an Anthropic API key; apps cannot use the claude.ai sign-in." if settings["kind"] == "agent_sdk" else ""))
        note.setWordWrap(True)
        form.addRow(note)
        self.forget_button = QPushButton("Forget stored key")
        self.forget_button.clicked.connect(self._forget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(self.forget_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _fetch(self):
        try:
            models = list_models(self.provider, self.key.text().strip(), self.base_url.text().strip())
        except Exception as error:
            QMessageBox.warning(self, "Fetch models", str(error))
            return
        current = self.model.currentText()
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(current if current in models or not models else models[0])
        self.model.showPopup()

    def _forget(self):
        config = load_config()
        config.get(self.provider, {}).pop("api_key", None)
        save_config(config)
        self.key.setPlaceholderText("stored key removed; paste a new key or rely on the environment")

    def save(self):
        config = load_config()
        entry = config.get(self.provider, {})
        if self.key.text().strip():
            entry["api_key"] = self.key.text().strip()
        entry["model"] = self.model.currentText().strip()
        entry["thinking"] = self.thinking.currentText()
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
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Interrupt what the assistant is waiting for; it then replies with what it has")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(CANCEL.set)
        bottom.addWidget(self.input, 1)
        bottom.addWidget(self.send_button)
        bottom.addWidget(self.stop_button)
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
        settings = provider_settings(name)
        self.status.setText(f"{key_status(name)} · model {settings.get('model') or 'default'} · thinking {settings.get('thinking', 'default')}")
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
        self.stop_button.setEnabled(True)
        CANCEL.clear()
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
            self.stop_button.setEnabled(False)
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()
