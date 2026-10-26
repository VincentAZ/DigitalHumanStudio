# Persistent milestone log

Read this file with `IMPLEMENTATION_PLAN.md` and `docs/SETUP_REPORT.md` before continuing.

## Current scope

User authorized **Milestone 1** after Milestone 0 completion. Preserve the host OS. Preserve diagnostics and stop at an Isaac compatibility failure before considering another architecture. Milestones 2–5 are not authorized.

| Milestone | Status | Evidence |
| --- | --- | --- |
| 0 — Reproducible runtime | Complete for standalone workers | Two full exit-0 runs: `diagnostics/20261026T164452-runtime/`; official checker, Mixar, media and dependency audit passed |
| 1 — Physical human baseline | Complete for standalone workers | Two 61/61 tracker passes, GPC rollout, video/trace/controller/restart audit: `diagnostics/20261026T180942Z-milestone1-acceptance/`; see `docs/MILESTONE1_REPORT.md` |
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

## 2026-10-26 UTC — User authorized repairs and continuation

- Applied a hash-guarded build-copy patch for explicit architecture markers. This cleared the original `pytetwild` conflict, exposing an unavailable `ovphysx` pin in an unrequested extra (`diagnostics/20261026T032127Z-patched-resolution/`).
- Restricted the lock profile to the complete base requirements plus `isaacsim`; excluded optional backend/test extras are listed in the emitted patch manifest. That profile resolves (`diagnostics/20261026T032232Z-isaac-profile-resolution/`).
- Combined ProtoMotions and its Isaac Lab requirements into the same resolver graph to prevent a later pip operation from replacing Isaac dependencies. The unpatched combination confirms the MoviePy 1.x/2.x conflict (`diagnostics/20261026T032429Z-combined-resolution/`).
- Added a recorded ProtoMotions build-copy patch allowing MoviePy >=1.0.3 and a fallback import for its image-sequence recording path. Isaac Lab still selects MoviePy 1.0.3 and Pillow 12.1.1. This changes one dependency floor and one import block; it is not an unmodified upstream source build. Vendor checkouts and source revisions remain unchanged.
- The combined patched profile resolves 269 packages with uv 0.11.32 (`diagnostics/20261026T032524Z-combined-patched-resolution/`). A full build is running in `diagnostics/20261026T032701.811084Z-runtime-build/`.
- Prepared a dependency audit covering selected extras and recording Isaac Lab's pre-existing declared overrides, plus a real encode/decode test for the patched recording path. Neither preparation nor resolution alone proves runtime compatibility. Media, GPU, physics, RTX, and repeat-run acceptance remain outstanding.
- The first full build stopped on a network timeout downloading `nvidia-nvtx-cu12==12.8.90`, after successful resolution. Retained its container, resolved lock, and a cache snapshot. Recovery in `diagnostics/20261026T033253Z-runtime-recovery/` resumes the exact lock with `uv sync --locked`, longer HTTP timeout and four concurrent downloads. No dependency re-resolution or architecture change was made.
- Future ordinary builds reuse `config/runtime.uv.lock` when present and refuse a stale lock via `uv sync --locked`. `scripts/check_media.sh` repeats the actual recording encode/decode test once an image exists.
- The long-lived NVIDIA downloads slowed sharply. Intentionally stopped the first recovery, preserved its container and cache image, and switched the two large rendering wheels to resumable HTTP ranges with final lock SHA-256 verification. Two CUDA wheels were prefetched from PyPI only after matching their filenames and hashes to the same NVIDIA-locked artifacts. This changes transport, not artifact versions.
- While inspecting the dependency audit, identified Numba 0.64.0's `numpy<2.5` requirement conflicting with the upstream broad override's selection of NumPy 2.5.4. Added the baseline constraint `numpy==2.3.1`, matching Isaac Sim kernel and satisfying Lab's `>=2` override. Resolution succeeded in `diagnostics/20261026T040231Z-numpy-compatible-lock/`; comparison confirms NumPy is the only package version changed.
- Prepared installation from the preserved cache and verified wheels in `diagnostics/20261026T040716Z-prefetched-runtime/`. Preloading these exact wheels will be followed by full `uv sync --locked` and the dependency audit; it does not bypass final dependency validation. Await the large Kit cache's completion before declaring installation or running runtime acceptance.
- Verified the two rendering archives and two CUDA archives against the lock. Direct wheel-path preloading was replaced with name/version installation through a local `--find-links` index because uv correctly replaced URL-origin installations during registry-locked sync. A small offline fixture verified registry-origin reuse before retrying the actual environment.
- Installation succeeded in `diagnostics/20261026T042235Z-registry-prefetched-runtime/`: 268 distributions, requested research versions, NumPy 2.3.1, Pillow 12.1.1, MoviePy 1.0.3, Torch 2.11.0+cu128. The combined dependency audit reports no unexpected violations. Raw `uv pip check` reports two exceptions: the exact Newton Git revision and Newton USD schemas required by Isaac Lab's existing overrides. These remain explicitly recorded; this is not a clean raw pip check.
- The final image is being saved. Recording, GPU computation, physics, RTX rendering, and restart acceptance still require execution.

- Saved final image `sha256:a233b5828caf801aabc6069c9e13169fb34fba8f365b0f72359b93e4b56055d9` and `config/runtime.uv.lock`. Media encode/decode passed in `diagnostics/20261026T044911-media/`.
- First runtime launch failed on root-owned package-local Kit cache/data paths. The wrapper rejected exit 0 without a report and retained the container (`diagnostics/20261026T044914-runtime/`). Corrected the launcher with a writable portable root, explicit log path and non-fast shutdown; the same-image retry is in progress. This is a launcher prerequisite failure, not evidence that replacing Ubuntu would help.

## 2026-10-26 UTC — Final runtime acceptance stopped

- The writable Kit portable root resolved cache/data permission errors. RTX initialized, ProtoMotions backend import and CUDA matrix multiplication succeeded, and the explicit GPU PhysX simulation completed 240 finite steps.
- The cube fell and reached the expected final resting height, but its center dipped to or below the required 0.20 m minimum. The minimum-height assertion failed. Python exited 1; launcher exited 4 and did not start the second run. Evidence: `diagnostics/20261026T045036-runtime/`, including full Kit log and retained container `studio-runtime-20261026T045036-1`.
- No successful saved RTX image or repeat-run acceptance exists. Trajectory export came after the failed assertion, so numeric samples are unavailable for this attempt. A future authorized diagnosis must capture them before assertions, inspect solver/contact settings and pose sampling, and retain the current threshold until evidence supports any revision.
- **Milestone 0 remains incomplete and stopped.** The dependency repair is complete, but the runtime is not accepted. No OS, driver, backend or architecture change was made. Milestone 1 remains unstarted.

## 2026-10-26 UTC — Contact diagnosis authorized; teardown failure preserved

- User requested trajectory capture and diagnosis of simulation settings versus measurement behavior; Milestone 1 remains gated on physics/render/restart success.
- Instrumented the test to persist every sampled position/velocity and an independent raw PhysX transform/velocity read before acceptance assertions. Also preserve configuration and initial/final scenes. At 60 Hz, the original failure reproduces with minimum z=0.18514985 m at step 34; cached/raw XYZ disagreement is zero (`diagnostics/20261026T160211-runtime/`).
- Changed only the integration frequency to 120 Hz, preserving four seconds of simulation (480 steps), a 0.5 s settling window and all thresholds. The cube stays at or above 0.24999999 m. All physics assertions pass. Saved and visually checked the RTX image (`diagnostics/20261026T160349-runtime/run-1.render.png`). No simulator/image/lock/driver/source change.
- The 120 Hz child wrote its completion report after app.close returned, then process termination failed with exit 139. Kernel journal confirms a segmentation fault in libomni.ui.so; Docker reports no OOM kill. The launcher correctly rejected the internal pass marker, retained the container and stopped before run 2.
- Preserved both containers, traces, scenes, configuration, logs, exit codes and a comparison plot in `diagnostics/20261026T160639Z-contact-analysis/`. Future reports distinguish internal assertions/cleanup return from full process success. No further Isaac run was attempted after the new lifecycle failure.
- **Milestone 0 remains incomplete.** Next is native teardown diagnosis and successful complete runs, then Milestone 1. No humanoid/model assets fetched and no architecture change made.

## 2026-10-26 UTC — Native teardown diagnosed; Milestone 0 accepted

- User authorized native teardown diagnosis and two complete runs. Captured GDB stacks showing late UI-window destruction through cached OSError tracebacks, then native event-subscription destruction during Python finalization. Failed trials and inspected-source hashes are preserved in `diagnostics/20261026T162432Z-teardown/`; no host or locked-image package installation occurred (GDB was diagnostic-container-only).
- Garbage collection, stat-cache reset/disable/detach and scoped slow teardown did not solve all upstream finalization defects. None of those cache experiments ships in the final launcher.
- Restored NVIDIA's default standalone shutdown mode, scoped simulation objects, explicitly cleared Isaac Lab's simulation context and USD stage, and forwarded failure exit status to SimulationApp.close. The parent accepts only checked artifacts/scene cleanup, Kit cleanup markers and final process exit 0. The slow/in-process teardown defect remains documented and outside the validated worker lifecycle.
- `scripts/check_runtime.sh` passed twice in `diagnostics/20261026T164452-runtime/`: each run completed 480 finite GPU PhysX steps at 120 Hz, gravity/contact/settling assertions, pinned backend import, CUDA math and RTX output; cleared scene/context; exited 0. Both images were visually inspected. The second run began after the first process terminated.
- A separate real intentional failure test exited 1 and produced no passing report. Existing official checker (two passes), Mixar save/render/reopen/desktop checks, recording encode/decode and installed dependency-audit evidence were re-inspected. Prior failed runs remain intact.
- **Milestone 0 is complete for separate standalone workers.** Host OS, NVIDIA driver, image, source pins and package lock are unchanged. A cold rebuild from empty cache is not claimed. Milestone 1 remains unstarted and must preserve its pretrained controller's own timing.

## 2026-10-26 UTC — Milestone 1 authorized and preparation verified

- User explicitly authorized M1. Updated current scope; M2–M5 remain unauthorized.
- Staged and hash-verified 44 pinned model, configuration, license, physical-asset and sample-motion files under ignored `.runtime/milestone1/assets/`; recorded `config/milestone1-assets.lock.json`.
- CPU-only checks in the accepted runtime image passed with exit 0: strict tracker/GPC checkpoint loading, finite saved weights, exact 23-body/66-joint MJCF ordering, 66 actions, 120 Hz physics / 30 Hz control, and self-contained GPC FSQ decoder construction. This is not physics or motion-quality acceptance.
- Recorded the publisher provenance discrepancy: `last_lab.ckpt` and legacy `last.ckpt` have identical LFS hashes at the pinned source revision despite different model-card descriptions.
- The BONES-SEED license has eligibility conditions not established by this session. Asked the user which eligibility category or separate license covers their use. Sample files were downloaded from the documented public GitHub location before this issue was found, but have not been loaded or executed. Future fetches exclude motion data by default.
- No M1 Isaac process, GPU simulation, motion trial, contact test, video or restart check has run. No host/image/source/package change, paid activation or later milestone work occurred.
- Evidence and precise remaining gates: `docs/MILESTONE1_REPORT.md`. Repeatable CPU check: `scripts/check_milestone1_preflight.sh`. Runtime work awaits the dataset clarification.

## 2026-10-26 UTC — Independent articulation probe; stopped at evidence gate

- Previous goal turn made concrete progress through pinned assets and passing CPU checks. Rechecked the clean worktree, accepted image and records; no live GPU job existed. Dataset eligibility remains unanswered.
- Added a one-second physical-asset probe independent of motion data and learned policies. Its container mounts only the physical asset directory and serialized configuration; it uses no MotionLib or checkpoint weights.
- The first attempt failed before simulator construction because the upstream recording setup wrote `output/renderings` beneath read-only `/opt/IsaacLab`. Preserved exit 1 and retained container under `diagnostics/20261026T171331Z-soma-articulation/`. Repaired only the launcher's working directory.
- The second attempt loaded 23 bodies and 66 joints, passed body/DOF permutation checks, instantiated all four contact sensors and recorded 30 finite zero-action steps at 120 Hz physics / 30 Hz control. It cleared the scene/context and exited 0. The wrapper returned 4 because Info-level shutdown markers were absent under the headless experience's Warn-level logging. No acceptance pass is claimed.
- Read-only trace analysis also found the default synthetic reset sits at the flat terrain's corner; feet move outside it and measured foot contact forces stay zero. This does not validate ground contacts, tracking or balance. Correcting the probe placement and explicit logging are proposed, not executed.
- Preserved full logs, both exit codes, configuration, mappings, scene, trace, converted USD files and hashes, and both containers. Further Isaac runs stopped at the failed evidence gate under AGENTS.md. Host, driver, image, pins and backend remain unchanged.
- The original M1 tracker trials, video, complete measurements and runtime GPC behavior remain unexecuted. Dataset eligibility still requires the user's answer. M1 is incomplete.

## 2026-10-26 UTC — Third-turn blocked audit

- Classified the previous goal turn as progress: it created physical articulation evidence and preserved the rejected runtime acceptance result. It was not a live-job wait.
- Rechecked authoritative state: worktree clean at `4bb4b84`, no running Docker containers, and both retained probe containers terminal (exit 1 for the launcher prerequisite; exit 0 for the run rejected by the parent evidence gate).
- The same unanswered BONES-SEED eligibility question has persisted across the initial M1 turn and two automatic continuations. No user eligibility statement or separate license has arrived. Independent CPU and articulation preparation is already recorded; motion trials cannot proceed on an assumed answer.
- Further Isaac runs also remain stopped under the explicit project failure rule. M1 still lacks accepted contacts/shutdown evidence, tracker trials, measurements/video, and runtime GPC behavior. No narrower preparation check establishes milestone completion.
- Goal marked blocked pending user input. All source/image/host constraints and diagnostics remain preserved; no new simulation was launched during this audit.

## 2026-10-26 UTC — User confirmed startup eligibility; continuation

- User answered the pending dataset question: “a startup below $1M annual revenue”. Recorded the statement in `config/milestone1-license.json`; no separate license or paid activation was inferred.
- Continuing the existing M1 request with the now-resolved prerequisite. Preserved previous failed probe results. Applied the diagnosed launcher/test-setup corrections only: explicit Info-level Kit logs and synthetic reset at (5, 5, 1.15), inside the flat terrain with clearance. Added an observed foot/toe contact force requirement (>1 N); no model/physics setting or source pin changed.
- Corrected probe validation is pending. A new compatibility failure will again stop execution with evidence.

- Corrected articulation probe passed (`diagnostics/20261026T173639Z-soma-articulation/`): 30 finite steps, 351.65 N maximum contact, child/wrapper exit 0, explicit scene cleanup and all required Kit shutdown records. CPU motion inventory found 61 tracker motions (418.93 s); the CPU inventory estimates up to 607 control frames, beyond the upstream default 600-frame cap. Runtime CUDA division rounds some clip lengths differently: the loaded simulator inventory requires 608 frames for the longest clip and 12,568 frames total; recording follows those runtime lengths. Full tracker recording started with only that cap lifted; frozen model/controller settings and evaluation thresholds remain unchanged.

## 2026-10-26 UTC — First tracker pass; GPC instrumentation stop and authorized correction

- Full tracker run passed in `diagnostics/20261026T174229Z-milestone1-tracker/`: 61/61 attempts successful, 12,568 complete 640×480 video frames at 30 fps, finite physical states/actions, exact joint/gain audit, verified contact measurements, exit 0 and accepted cleanup. Original evaluator mean body-position error: 0.071711 m.
- GPC executed 600 finite recorded frames, then failed the contact assertion (`diagnostics/20261026T175358Z-milestone1-gpc/`, child 1/wrapper 4). Preserved container, commands, logs, snapshots, video/trace and hashes; stopped further Isaac runs. Saved configuration proves `robot.contact_bodies=None` and an empty actual sensor map. ProtoMotions returns zero-filled force buffers without sensors; this is an unavailable measurement prerequisite, not evidence of absent physical contact or backend incompatibility.
- Prepared a correction enabling the four foot/toe sensors and checking their presence before inference. GPC has `observe_contacts=false`, so the sensors do not add policy inputs; weights, gains, timing and backend are unchanged. User explicitly authorized: “Resume corrected validation”. Rerunning the corrected GPC test, then the full tracker restart check. Historical failure evidence remains unchanged.

## 2026-10-26 UTC — Milestone 1 accepted

- Corrected GPC run passed (`diagnostics/20261026T175823Z-milestone1-gpc/`): 600 complete finite frames, 1,486.49 N maximum measured contact, video/trace validation and clean standalone shutdown. The added measurement sensors did not change any of the 600 actions, joint positions or body positions relative to the preserved earlier rollout. No task-success claim or training.
- Second full tracker process passed (`diagnostics/20261026T175955Z-milestone1-tracker/`): 61/61 successful attempts, 12,568 complete video frames, child and parent exit 0, checked scene/context cleanup and all shutdown log markers. All 61 traces are byte-identical to the first process; all per-motion metrics and outcomes match.
- Independent CPU audit verified finite values, dimensions, monotonic clocks, quaternion norms, complete frame counts and every actual joint gain/armature/effort/velocity limit against the frozen configuration. All 777 accepted-run artifact files rehashed successfully. The exact audit command, source snapshot, exit 0 and aggregate result are in `diagnostics/20261026T180942Z-milestone1-acceptance/`.
- Recorded acceptance in `config/milestone1.json`; updated README, baseline, setup/provenance records and the full M1 report with commands, measurements, video links, license confirmation, preserved failures and limitations. Python compilation, shell syntax and project whitespace checks passed.
- No OS, NVIDIA driver, image, package-lock, pinned-source or backend change. Vendor checkouts remain clean; no simulation containers remain running. The accepted mode remains separate standalone workers. Videos are timed at 30 fps; full recording throughput was approximately 20 control frames per wall-clock second, not a realtime UI benchmark.
- **Milestone 1 is complete.** This reproduces pretrained tracking and prior inference; it is not a newly learned skill. Milestones 2–5 remain unstarted and unauthorized.
