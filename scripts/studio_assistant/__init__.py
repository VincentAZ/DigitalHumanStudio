"""Director's assistant: an AI model that drives the studio through the same operations the control
center's buttons use. Provider-agnostic; tools are plain functions over the project's files and
launchers (see tools.py), so the assistant can only do what the interface can do.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
CONFIG = ROOT / "config"
RUNTIME = ROOT / ".runtime"
ARTIFACTS = ROOT / "artifacts"
TRANSCRIPTS = ARTIFACTS / "assistant"
