#!/usr/bin/env bash
# Launch the Digital Human Studio control center (PySide6 desktop application).
# The interface runs on the host in its own pinned Python 3.12 environment; simulation,
# training and evaluation still run through the recorded launchers in the locked image.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
venv="$project_root/.runtime/studio-app"
python="$project_root/.runtime/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3"
uv=$(ls "$project_root"/.runtime/tools/uv-*/uv-x86_64-unknown-linux-gnu/uv 2>/dev/null | head -1 || true)
requirements="$project_root/config/studio-app-requirements.txt"
if [[ ! -x "$venv/bin/python" ]]; then
    [[ -x "$python" && -x "$uv" ]] || { echo 'Pinned Python 3.12 or uv missing; run python3 scripts/install_local_tools.py.' >&2; exit 2; }
    "$uv" venv --python "$python" "$venv"
    "$uv" pip install --python "$venv/bin/python" --require-hashes -r "$requirements"
fi
export PYTHONPATH="$project_root/scripts${PYTHONPATH:+:$PYTHONPATH}"
exec "$venv/bin/python" -m studio_app "$@"
