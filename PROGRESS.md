# Persistent milestone log

Read this file with `IMPLEMENTATION_PLAN.md` and `docs/SETUP_REPORT.md` before continuing.

## Current scope

User authorized **Milestone 0 only**. Preserve the host OS. Preserve diagnostics and stop at an Isaac compatibility failure before considering another architecture.

| Milestone | Status | Evidence |
| --- | --- | --- |
| 0 — Reproducible runtime | Stopped; dependency resolution failed | Official Isaac checker passed twice; Mixar checks passed; final runtime untested |
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
- Validated shell syntax, Python compilation, source manifest checksums, and project-source Git whitespace. Unmodified upstream snapshots and raw logs retain their original trailing whitespace. Initial Git history uses an explicit bootstrap identity because no user identity was configured.

Next: user runs `sudo bash scripts/install_host_tools.sh` in a local terminal. After host tooling is installed, run the official Isaac checker before building the pinned learning runtime. Stop on compatibility failure. Do not start Milestone 1. No OS, NVIDIA driver, security-policy, or architecture change has been made.

## 2026-10-25 — First continuation / prerequisite recheck

- Previous turn made progress: created committed documentation and diagnostics, installed local tools, and passed Mixar checks.
- Rechecked authoritative machine state: Docker and `nvidia-ctk` remain absent; `sudo -n true` still requires interactive authentication; no root package installer or Docker daemon was observed running.
- Fixed the Isaac launcher's diagnostic preservation: unsuccessful checker runs retain their stopped container; a log-copy failure also retains it and stops the launcher. Only successful checks with copied logs remove the container.
- Exercised checker failure, log-copy failure, and success with an isolated mock Docker command; verified exit codes 4/5/0 and preservation/removal behavior. Shell syntax and whitespace checks passed. These tests do not establish Isaac compatibility.
- The same authentication prerequisite remains outstanding. Milestone 0 stays incomplete and Isaac remains untested.

## 2026-10-25 — Second continuation / blocked audit

- Previous turn made progress by correcting and testing diagnostic preservation.
- Rechecked the machine: Docker and NVIDIA Container Toolkit are still absent, noninteractive sudo still requires authentication, and no host installer or Docker daemon was observed running.
- The same prerequisite has blocked three consecutive goal turns. Further runtime validation requires the user's local authenticated bootstrap step. Goal marked blocked; Milestone 0 remains incomplete, not failed on compatibility grounds.
- Resume after `sudo bash scripts/install_host_tools.sh` completes. Preserve the current stack and host OS; run the Isaac compatibility gate next.

## 2026-10-26 UTC — User completed host bootstrap

- Verified Docker 29.1.3 and NVIDIA Container Toolkit 1.20.1 packages, Git LFS, and Vulkan tools. Docker service is active and its configuration registers the NVIDIA runtime.
- The user's account now belongs to `docker`, but the existing agent process retains its old groups. The wrapper's `sg` dependency is absent on this Ubuntu installation; corrected the bootstrap to include `util-linux-extra`, and requested that one-package repair from the user. No repeat installation of Docker is needed.
- Fresh host and package/group/configuration evidence: `diagnostics/20261026T012503.739621Z/`.
- Fetched detached source checkouts at both requested revisions into ignored `vendor/IsaacLab` and `vendor/ProtoMotions`. LFS smudging was disabled during fetch; these are source checkouts only, not installed environments or downloaded model assets.
- Isaac remains untested until this session can access Docker. Continue with `scripts/check_isaac.sh` once `sg` is installed.

## 2026-10-26 UTC — Docker access verified; compatibility run started

- User installed the missing group-refresh utility. `scripts/docker.sh version` successfully contacted Docker client and daemon, both 29.1.3.
- Recorded installed host package versions in `config/host-tools.json` and refreshed diagnostics in `diagnostics/20261026T013048.738346Z/`.
- Started `scripts/check_isaac.sh`; pulling the pinned Isaac Sim 6.0.0 image. Await the running process's result before any retry or pinned runtime installation.
- Prepared a guarded container builder and final-environment smoke checks while the 10.7 GB compressed image downloads. Syntax checks passed; neither builder nor smoke has executed. They do not count as completed acceptance evidence.

## 2026-10-26 UTC — Official compatibility gate passed

- Downloaded and locked Isaac Sim 6.0.0 image digest `sha256:68735a60b6c15c85e0dd0098570c6d2cc79e928f2d068ce2790aa43284ac165d`. Container userspace is Ubuntu 24.04.3, bundled Python is 3.12.13.
- First preflight stopped because the image provides `./python.sh`, not a `python3` command on PATH. Corrected the launcher. This was a launcher error before Isaac executed; the evidence is retained in `diagnostics/20261026T012936-isaac/`.
- Both actual official checker runs exited 0 and reported `System checking result: PASSED`. Container GPU visibility and Vulkan detection succeeded. Evidence: `diagnostics/20261026T020033-isaac/`, including copied Kit logs.
- Preserved warnings about Hub startup, headless display, CPU powersave governor, and IOMMU. No host settings were changed to suppress them.
- The first source-staging attempt invoked Git LFS filters and fetched small upstream test fixtures. Interrupted that staging process before Docker build and fixed `git archive` to set `GIT_LFS_SKIP_SMUDGE=1`. Their hashes are preserved under `diagnostics/20261026T020145.113355Z-runtime-build/`.
- The guarded build started in `diagnostics/20261026T020231.007421Z-runtime-build/`; its failure and the final stopping point are recorded below.

## 2026-10-26 UTC — Pinned runtime build stopped

- The documented `uv sync --python 3.12.13 --extra isaacsim` step exited 1. uv reports conflicting `pytetwild==0.2.3` and `pytetwild[all]>=0.3.0,<0.4` requirements in a marker branch containing both x86_64 and ARM conditions. This occurs before the final environment is installed.
- Tested a resolver-only Linux x86_64 restriction in a disposable copy, then the same restriction with verified uv 0.13.5. Both dry runs exited 1 with the same error. Source revisions and package requirements were not changed. The unsuccessful restriction is preserved as a diagnostic experiment and is not part of the build configuration. The configured baseline remains uv 0.11.32.
- Preserved the original failed build container, two diagnostic containers, a snapshot image, complete logs/exit codes, original build inputs, trial configuration patch, and publisher metadata. See `diagnostics/20261026T020231.007421Z-runtime-build/README.md` and `stopped-result.json`.
- **Milestone 0 remains incomplete and is stopped at this dependency compatibility barrier.** No final image lock or resolved package lock exists. Final GPU computation, physics, RTX rendering, shutdown, and repeat-run checks were not executed.
- The official checker pass does not establish full-stack compatibility; the resolver failure also does not demonstrate that the Ubuntu 26.04 host is incompatible. Changing the host OS is not an evidenced remedy for this dependency error.
- No OS, NVIDIA driver, research source revision, backend, or architecture was changed. Milestones 1–5 remain unstarted. Resume requires a reviewed resolution of the pinned environment failure; do not silently change pins or substitute a backend.

## 2026-10-26 UTC — User asked how to resolve the failure

- Isolated the architecture-marker issue in an offline metadata-only reproduction using uv 0.11.32 and synthetic local wheels. Substring membership markers reproduce the same impossible branch (exit 1); explicit architecture equality alternatives resolve successfully (exit 0).
- Evidence: `diagnostics/20261026T024641Z-marker-repro/`. This identifies a narrow candidate metadata patch without changing package versions; it does not validate the real dependency graph or runtime.
- No fix has been applied to the active build recipe. Next is to test a recorded build-time marker patch against the full graph, then review any further conflicts. The pinned Isaac Lab root requests MoviePy 1.x while ProtoMotions requests 2.x; their final combined environment must also be checked before acceptance.
