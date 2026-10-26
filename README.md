# Digital Human Research Studio

Local Linux research studio for character authoring and learned physical movement.

Only **Milestone 0: reproducible runtime** is currently authorized. **Stopped, incomplete:** NVIDIA's official compatibility checker passed twice and Mixar checks passed, but the pinned learning environment failed dependency resolution. Diagnostics are preserved; physics and RTX rendering remain untested. See the setup report before resuming.

- [Implementation specification](IMPLEMENTATION_PLAN.md)
- [Milestone log](PROGRESS.md)
- [Machine and setup evidence](docs/SETUP_REPORT.md)
- [Requested dependency baseline](config/baseline.json)
- [Provenance and license record](docs/PROVENANCE.md)

Run `python3 scripts/inspect_host.py` to capture a fresh read-only machine report in `diagnostics/`. See the setup report for installation and validation steps. The original planning document is retained unchanged as `PLAN.md`.

Mixar 4.3.5 and project-local uv/Python 3.12 are installed. `scripts/check_mixar.sh` repeats the authoring smoke checks. Recreate those local tools with `python3 scripts/install_local_tools.py`. Docker and NVIDIA Container Toolkit are installed and accessible through `scripts/docker.sh`. Consult the setup report before starting a build or GPU check.
