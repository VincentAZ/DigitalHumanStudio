# Digital Human Research Studio

Local Linux research studio for character authoring and learned physical movement.

**Milestone 0 is complete** on the existing host. The pinned runtime passed two complete GPU physics/render/shutdown runs, and the official Isaac checker, Mixar and video recording checks passed. The launcher uses Kit's supported standalone shutdown; the native slow-shutdown defect and diagnostics are documented in the [setup report](docs/SETUP_REPORT.md). **Milestone 1 is also complete:** the SOMA tracker passed all 61 motions in two fresh processes, and the compatible GPC prior completed its recorded rollout. See the [M1 report and recordings](docs/MILESTONE1_REPORT.md). Milestone 2 has not started. Host OS and NVIDIA driver are unchanged.

- [Control center (desktop interface)](docs/CONTROL_CENTER.md) — `scripts/studio.sh`
- [Implementation specification](IMPLEMENTATION_PLAN.md)
- [Milestone log](PROGRESS.md)
- [Machine and setup evidence](docs/SETUP_REPORT.md)
- [Requested dependency baseline](config/baseline.json)
- [Provenance and license record](docs/PROVENANCE.md)

Run `python3 scripts/inspect_host.py` to capture a fresh read-only machine report in `diagnostics/`. See the setup report for installation and validation steps. The original planning document is retained unchanged as `PLAN.md`.

**Control center:** `scripts/studio.sh` opens the desktop interface (the Astra redesign, hosted in Qt WebEngine inside a PySide6 window) for live direction of the character; it drives the recorded launchers below and is described in [docs/CONTROL_CENTER.md](docs/CONTROL_CENTER.md). The character is moved by the tracker-driven walker: the Milestone 1 tracker following a reference composed from licensed clips, which walks to a clicked point and stands still without training (Milestone 3's three RL training attempts never met the 90/100 gates; training was retired to `sandbox/rl-training/`). A small industrial work-cell scene (`config/scenes/`) can be loaded. A director's assistant panel (Claude via the Agent SDK, or OpenAI, Gemini, Grok, OpenRouter and a local LM Studio; your own keys) drives the same operations by chat; the project direction is recorded in [docs/DIRECTION.md](docs/DIRECTION.md).

Mixar 4.3.5 and project-local uv/Python 3.12 are installed. `scripts/check_mixar.sh` repeats the authoring smoke checks. Recreate those local tools with `python3 scripts/install_local_tools.py`. Docker and NVIDIA Container Toolkit are installed and accessible through `scripts/docker.sh`. Consult the setup report before starting a build or GPU check.
