#!/usr/bin/env bash
# Use new Docker group membership without changing the login session.
set -euo pipefail
if ! command -v docker >/dev/null; then
    echo 'Docker is missing. See docs/SETUP_REPORT.md.' >&2
    exit 2
fi
if [[ -r /var/run/docker.sock && -w /var/run/docker.sock ]]; then
    exec docker "$@"
fi
if id -nG "$(id -un)" | tr ' ' '\n' | grep -qx docker; then
    printf -v docker_command '%q ' docker "$@"
    exec sg docker -c "$docker_command"
fi
echo 'Docker access unavailable. Run the host bootstrap and start a new login session.' >&2
exit 2
