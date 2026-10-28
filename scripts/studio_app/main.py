"""Main window of the Digital Human Studio control center.

The interface is the Astra redesign (HTML/CSS/JS in ``scripts/studio_app/web``) hosted in Qt
WebEngine; ``bridge.Bridge`` connects it to the launchers, the live worker files and the
assistant. ``STUDIO_DEVTOOLS=<port>`` exposes Chromium's remote debugging on localhost.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QFile, QUrl
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from studio_app import APP_LOG
from studio_app.bridge import Bridge
from studio_app.jobs import JobCenter

WEB = Path(__file__).resolve().parent / "web"


class StudioPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        try:
            with APP_LOG.open("a") as stream:
                stream.write(f"[page] {Path(source).name}:{line} {message}\n")
        except OSError:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Human Studio")
        self.resize(1600, 1000)
        self.jobs = JobCenter(self)
        self.bridge = Bridge(self.jobs, self)
        self.view = QWebEngineView(self)
        self.page = StudioPage(self.view)
        self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor("#141516"))
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        self._inject_webchannel_js()
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(str(WEB / "index.html")))
        self.setCentralWidget(self.view)

    def _inject_webchannel_js(self):
        """qwebchannel.js ships inside QtWebChannel's resources; inject it before the page's own scripts run."""
        resource = QFile(":/qtwebchannel/qwebchannel.js")
        if not resource.open(QFile.OpenModeFlag.ReadOnly):
            raise RuntimeError("qwebchannel.js resource missing from the Qt build")
        script = QWebEngineScript()
        script.setName("qwebchannel")
        script.setSourceCode(bytes(resource.readAll()).decode("utf-8"))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self.page.scripts().insert(script)

    def closeEvent(self, event):
        if self.bridge.session_active():
            box = QMessageBox(QMessageBox.Icon.Question, "Session still running",
                              "A live session is running. End it, or leave it running in the background? "
                              "Either way it finishes on its own and records its evidence; reopening the studio reattaches to a session left running.",
                              QMessageBox.StandardButton.Cancel, self)
            end = box.addButton("End session and close", QMessageBox.ButtonRole.AcceptRole)
            leave = box.addButton("Leave it running", QMessageBox.ButtonRole.DestructiveRole)
            box.setDefaultButton(end)
            box.exec()
            if box.clickedButton() not in (end, leave):
                event.ignore()
                return
            if box.clickedButton() is end and not self.bridge.end_for_close():
                for job in self.jobs.active():
                    job.terminate()
        self.bridge.assistantNew()
        event.accept()


def run(argv: list[str]) -> int:
    port = os.environ.get("STUDIO_DEVTOOLS")
    if port:
        os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = port
    app = QApplication(argv)
    app.setApplicationName("Digital Human Studio")
    app.setDesktopFileName("digital-human-studio")   # matches the entry scripts/install_desktop_launcher.sh writes
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "icon.svg")))
    window = MainWindow()
    window.show()
    return app.exec()
