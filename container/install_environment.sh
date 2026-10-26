#!/usr/bin/env bash
# Execute the pinned upstream installation sequence inside Ubuntu 24.04.
set -euo pipefail
cd /opt/IsaacLab
uv python install 3.12.13 --no-bin
managed_python=$(uv python find 3.12.13)
"$managed_python" /opt/studio/configure_protomotions.py
"$managed_python" /opt/studio/configure_target.py --combine-protomotions
if [[ -f /opt/studio/locks/runtime.uv.lock ]]; then
    cp /opt/studio/locks/runtime.uv.lock uv.lock
    uv sync --locked --python 3.12.13 --extra isaacsim
else
    uv sync --python 3.12.13 --extra isaacsim
fi
bash /opt/studio/finish_environment.sh
