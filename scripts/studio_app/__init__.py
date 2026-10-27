"""Digital Human Studio control center (PySide6 desktop application).

The package finds the project from its own location so it never depends on the caller's
working directory. All simulation, training and evaluation work is delegated to the
existing recorded launchers in ``scripts/``; the interface only starts them, sends live
commands and reads their outputs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
ARTIFACTS = ROOT / "artifacts" / "milestone3"
DIAGNOSTICS = ROOT / "diagnostics"
RUNTIME = ROOT / ".runtime"
CONFIG = ROOT / "config"
APP_LOG = RUNTIME / "studio-app.log"
LIVE_POINTER = RUNTIME / "studio-live-current.json"
GPU_LOCK = RUNTIME / "studio-gpu.lock"
