#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
binary="$project_root/.runtime/mixar/Mixar-4.3.5-linux-x86_64/mixar-launcher"
if [[ ! -x "$binary" ]]; then
    echo 'Pinned Mixar binary missing; run python3 scripts/install_local_tools.py.' >&2
    exit 2
fi
exec "$binary" "$@"
