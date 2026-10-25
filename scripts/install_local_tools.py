#!/usr/bin/env python3
"""Install hash-verified project-local Mixar and uv, leaving system Python alone."""
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def install(component, destination):
    archive = ROOT / ".downloads" / component["url"].rsplit("/", 1)[1]
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + ".partial")
        with urllib.request.urlopen(component["url"], timeout=60) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        partial.rename(archive)
    with archive.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != component["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch: {archive}; preserving it for inspection")
    # Never overlay an existing installation, which might contain user changes.
    target = ROOT / ".runtime" / destination
    if not target.exists() or not any(target.iterdir()):
        with tarfile.open(archive) as bundle:
            bundle.extractall(target, filter="data")
    print(f"Verified archive: {archive.name}: {actual}")


def main():
    baseline = json.loads((ROOT / "config/baseline.json").read_text())
    install(baseline["mixar"], "mixar")
    install(baseline["uv"], "tools")
    uv = ROOT / ".runtime/tools/uv-x86_64-unknown-linux-gnu/uv"
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(ROOT / ".runtime/python"))
    subprocess.run([str(uv), "python", "install", "3.12.13", "--no-bin"], env=env, check=True)


if __name__ == "__main__":
    main()
