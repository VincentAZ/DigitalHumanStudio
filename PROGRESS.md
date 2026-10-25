# Persistent milestone log

Read this file with `IMPLEMENTATION_PLAN.md` and `docs/SETUP_REPORT.md` before continuing.

## Current scope

User authorized **Milestone 0 only**. Preserve the host OS. Preserve diagnostics and stop at an Isaac compatibility failure before considering another architecture.

| Milestone | Status | Evidence |
| --- | --- | --- |
| 0 — Reproducible runtime | Incomplete; prerequisite authentication needed | Host diagnostics and Mixar checks passed; Isaac not yet tested |
| 1 — Physical human baseline | Not started | Not authorized in current scope |
| 2 — Detailed character | Not started | — |
| 3 — Walking | Not started | — |
| 4 — Second skill | Not started | — |
| 5 — Desktop studio | Not started | — |

## 2026-10-25 — Workspace and baseline inspection

- Confirmed renamed workspace `DigitalHumanStudio`; only the original plan existed.
- Initialized Git on `main`; created persistent specification, instructions, requested version manifest, and diagnostic scripts.
- Captured hardware, OS, GPU, tools, privilege and user-namespace probes in `diagnostics/20261025T235204.379599Z/host.json`.
- Verified pinned upstream source metadata and Mixar release digest. Root `uv.lock` at the pinned Isaac Lab revision returned HTTP 404; retain the failed lookup and resolve a real environment lock during installation.
- Prepared host tooling bootstrap and official Isaac checker launcher. Neither is an executed compatibility pass.
- Requested local terminal authentication for host tooling; the session cannot supply the user's sudo password. No privilege restrictions were disabled.
- Mixar 4.3.5 archive downloaded, SHA-256 matched the publisher's release digest, and extracted under `.runtime/mixar/`. Save, CPU render, second-process reopen, and desktop open/clean shutdown passed. NVIDIA OpenGL device confirmed; UI warnings retained. Evidence: `diagnostics/20261025T235551-mixar/`.
- Installed project-local uv 0.11.32 and CPython 3.12.13. Repeated the local installer successfully. System Python was preserved.
- Ran the Isaac launcher prerequisite gate: exit 2, Docker absent. This is a blocked test, not an Isaac compatibility failure.
- Validated shell syntax, Python compilation, source manifest checksums, and Git whitespace. Initial Git history uses an explicit bootstrap identity because no user identity was configured.

Next: user runs `sudo bash scripts/install_host_tools.sh` in a local terminal. After host tooling is installed, run the official Isaac checker before building the pinned learning runtime. Stop on compatibility failure. Do not start Milestone 1. No OS, NVIDIA driver, security-policy, or architecture change has been made.
