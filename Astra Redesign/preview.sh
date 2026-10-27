#!/usr/bin/env bash
set -euo pipefail
mockup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -m http.server "${1:-8787}" --bind 127.0.0.1 --directory "$mockup_dir"
