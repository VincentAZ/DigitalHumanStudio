#!/usr/bin/env bash
# Execute the pinned upstream installation sequence inside Ubuntu 24.04.
set -euo pipefail
cd /opt/IsaacLab
uv python install 3.12.13 --no-bin
managed_python=$(uv python find 3.12.13)
"$managed_python" /opt/studio/configure_protomotions.py
"$managed_python" /opt/studio/configure_target.py --combine-protomotions
uv sync --python 3.12.13 --extra isaacsim
cp uv.lock /opt/studio/runtime.uv.lock
python_bin=/opt/IsaacLab/.venv/bin/python
"$python_bin" /opt/studio/verify_dependencies.py
uv pip freeze --python "$python_bin" > /opt/studio/requirements.freeze.txt
uv pip list --python "$python_bin" --format json > /opt/studio/packages.json
dpkg-query -W > /opt/studio/container-packages.txt
"$python_bin" - <<'PY'
import importlib.metadata as metadata
import json
import platform
from pathlib import Path
expected = {"isaacsim": "6.0.0.1", "isaaclab": "12.0.0", "protomotions": "3.1.0"}
observed = {name: metadata.version(name) for name in expected}
assert observed == expected, (expected, observed)
assert platform.python_version() == "3.12.13", platform.python_version()
Path('/opt/studio/versions.json').write_text(json.dumps({
    "python": platform.python_version(), "packages": observed,
    "status": "installed_not_runtime_validated"
}, indent=2) + '\n')
PY
