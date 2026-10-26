# Milestone 0 setup report

Status: **Milestone 0 complete for standalone simulation workers. Two full GPU physics/RTX/shutdown runs passed with process exit 0. Dependency audit, official checker, Mixar and recording checks passed. Native slow/in-process teardown remains defective and is not the supported launcher mode.**

## Current repair — 2026-10-26 UTC

Successful installation evidence: `diagnostics/20261026T042235Z-registry-prefetched-runtime/`. The 268 installed distributions include Isaac Sim 6.0.0.1, Isaac Lab 12.0.0, ProtoMotions 3.1.0, NumPy 2.3.1, Pillow 12.1.1, MoviePy 1.0.3, and Torch 2.11.0+cu128 on Python 3.12.13. `environment/dependency-audit.json` has no unexpected violations. Raw `uv pip check` reports two mismatches intentionally introduced by the pinned Isaac Lab source: Newton 1.4.0.dev0 at commit `c7ae7c7648cd0717df39e5c94b95d5a02c997320` instead of Isaac Sim's 1.2.0 requirement, and Newton USD schemas 0.6.0 satisfying Lab's >=0.3.1 override instead of Sim's 0.2.0 requirement. Those exceptions are preserved, not presented as a clean raw pip check. The image is locked in `config/runtime-image.lock` and the combined package lock in `config/runtime.uv.lock`. Runtime acceptance passed twice with the standalone lifecycle described below.

The build keeps the requested source revisions but applies explicit, hash-guarded patches to copies inside the container. The ignored vendor checkouts remain pristine. Every modification produces a unified diff and before/after hashes under `/opt/studio` for collection with the final build evidence.

- `container/configure_target.py` replaces architecture substring checks with equality alternatives and limits the universal lock to Linux x86_64, the base requirements, and the `isaacsim` extra. Unused extras are excluded from this target profile because uv otherwise resolves their unavailable optional backend packages. This preserves the selected Isaac dependency requirements.
- `container/configure_protomotions.py` lowers the MoviePy dependency floor from 2 to 1.0.3 and adds a fallback import for the 1.x image-sequence class. The combined graph selects MoviePy 1.0.3 and keeps Isaac's Pillow 12.1.1. This is a documented compatibility patch, not an unmodified upstream build; other MoviePy functionality is outside the test scope.
- ProtoMotions and `requirements_isaaclab.txt` now resolve in the Isaac Lab root project so the final environment has one combined `runtime.uv.lock`. The previous sequential installation could otherwise replace Isaac dependencies.
- The baseline constrains NumPy to 2.3.1, matching Isaac Sim kernel and satisfying both Lab's `>=2` override and Numba 0.64.0's `<2.5` bound. Without that constraint, the broad override selected incompatible NumPy 2.5.4. `diagnostics/20261026T040231Z-numpy-compatible-lock/lock-changes.json` confirms that this repair changes only NumPy in the prior resolution.
- Isaac Lab's original dependency overrides remain unchanged. The installed-environment audit preserves raw `uv pip check` output and separately checks default and selected-extra requirements. Only mismatches matching those explicit upstream overrides can be accepted; a Git override must match the installed commit. Such exceptions remain visible in `dependency-audit.json` and must not be described as a clean pip check.

The combined dry run resolved 269 packages using uv 0.11.32. Installation ultimately succeeded with the NumPy-compatible lock. The earlier full build and download recoveries are preserved:

| Evidence directory under `diagnostics/` | Outcome |
| --- | --- |
| `20261026T032524Z-combined-patched-resolution/` | Combined graph resolved before the NumPy correction |
| `20261026T032701.811084Z-runtime-build/` | NVIDIA wheel HTTP timeout; failed container and lock retained |
| `20261026T033253Z-runtime-recovery/` | Locked retry deliberately stopped after transfers slowed; cache snapshot retained |
| `20261026T040231Z-numpy-compatible-lock/` | Resolved corrected lock; only NumPy version changed |
| `20261026T040716Z-prefetched-runtime/` | Direct-path wheel preloading caused uv to replace URL-origin packages; deliberately stopped |
| `20261026T042235Z-registry-prefetched-runtime/` | Registry-origin local wheel preloading followed by complete locked sync and passing dependency audit |

`scripts/fetch_locked_wheels.py` downloads large wheels in resumable ranges and accepts an assembled archive only when its SHA-256 matches the lock. CUDA mirrors require the identical filename and hash from PyPI. Four verified wheels were preloaded through a local `--find-links` registry index in the successful recovery; other prefetched archives were fallback cache only. This changed download transport, not package versions. Build inputs, commands, patch manifests, installed packages, raw checks and transport provenance are retained with the successful installation.

A full clean rebuild from an empty cache has not been completed. The final image comes from the retained build cache followed by `uv sync --locked` and the installed-environment audit. The ordinary builder reuses `config/runtime.uv.lock` with `--locked`; network availability remains necessary for a clean rebuild. No OS, driver, simulation backend or source revision was changed, and no later milestone was started.

## Runtime launcher validation

The recording encode/decode test passed in `diagnostics/20261026T044911-media/`, with all 12 frames, 12 fps, and expected decoded colors. The video is under `artifacts/milestone0/media-20261026T044911/`. It exercises the actual patched import block and image-sequence class, not every MoviePy feature.

The first runtime attempt (`diagnostics/20261026T044914-runtime/`) failed because Kit tried to create shader caches and data inside the root-owned Python installation. Its process returned 0 but produced no completion report; the wrapper correctly rejected it and retained the container. Kit could not create its announced file log; complete stdout/stderr are preserved. The launcher now passes a user-writable [Kit portable root](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/configuring.html) and an explicit output log path. An earlier launcher disabled fast shutdown to write its completion report after cleanup. Native teardown diagnosis showed that this override exposes late Python destructors after Kit unloads. The final launcher restores the default standalone lifecycle and leaves final acceptance to the parent after process exit. It explicitly prints exceptions and preserves their nonzero status. The image, host, driver and backend are unchanged.

## Accepted runtime and native teardown diagnosis

Final evidence: `diagnostics/20261026T164452-runtime/`. Both runs use the same locked image and passed every check independently, with exit 0. The second process started after the first terminated. Both 640×480 RTX images were visually inspected and show the expected blue cube on the floor.

| Check | Run 1 | Run 2 |
| --- | --- | --- |
| CUDA computation / pinned ProtoMotions import | Passed | Passed |
| GPU PhysX, 120 Hz, four seconds | 480 finite steps | 480 finite steps |
| Minimum cube center height (>0.20 m) | 0.24999999 m | 0.24999999 m |
| Final center height (0.25 ±0.03 m) | 0.25 m | 0.25 m |
| Final 0.5 s maximum speed (<0.1 m/s) | 0.00012403 m/s | 0.00012403 m/s |
| Cached/raw XYZ disagreement | 0 m | 0 m |
| RTX image / scene and trajectory saved | Passed | Passed |
| Simulation singleton cleared / USD stage closed | Verified | Verified |
| Kit cleanup milestones / final process exit | Verified / 0 | Verified / 0 |

The [contact diagnosis](../diagnostics/20261026T160639Z-contact-analysis/README.md) preserved the original 60 Hz failure. At that frequency the cube travels 98.10 mm during the impact step before correction, dipping to 0.18515 m. Cached and raw PhysX positions agree exactly. At 120 Hz the same four-second test passes without relaxing any threshold. This M0 integration frequency does not set the timing of later pretrained controllers.

The [native teardown report](../diagnostics/20261026T162432Z-teardown/README.md) contains GDB traces of a UI-window destructor reached through an OSError traceback during `Py_FinalizeEx`, and a later native event-subscription destructor after a cache experiment. Garbage collection, stat-cache changes and explicit object cleanup did not make `fast_shutdown=False` reliable. Those experiments remain diagnostics only.

The final launcher uses [NVIDIA's default standalone shutdown](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/source/extensions/isaacsim.simulation_app/docs/index.html), scopes simulation objects, explicitly clears the simulation context/stage, and calls `app.close(wait_for_replicator=True, skip_cleanup=False, exit_code=...)`. It writes a pending-shutdown result before Kit terminates the process. The parent requires checked scene cleanup, Kit's Replicator/shutdown log markers and exit 0; a child marker alone cannot pass. A real intentional RuntimeError test returned 1 with no passing report (`diagnostics/20261026T162432Z-teardown/negative-exit.*`). No application-level forced-success exit or library/cache patch ships in the launcher.

**Scope:** separate standalone worker processes are validated. The upstream slow/in-process finalization defect remains unresolved; repeated Kit startup in one Python interpreter is not claimed. Known Hub/headless/powersave/IOMMU warnings remain in the logs. GDB was installed only in a disposable diagnostic container. Host OS, NVIDIA driver, pinned source revisions, final image and package lock are unchanged.

**Milestone 1 update:** the user subsequently authorized M1. Pinned physical/model assets are staged and CPU-only model/contract checks passed; physics trials are pending dataset eligibility clarification. See [the M1 report](MILESTONE1_REPORT.md). The historical M0 observations below remain unchanged.

## Inspected host — 2026-10-25

The actual workspace is `/home/vincent/Repos/DigitalHumanStudio`. It initially contained only `PLAN.md`, with no Git repository or existing project instructions. The original plan remains unchanged; `IMPLEMENTATION_PLAN.md` records the renamed path and current execution scope.

| Item | Observed |
| --- | --- |
| OS | Ubuntu 26.04.1 LTS, x86_64 |
| Kernel | 7.0.0-38-generic |
| CPU | AMD Ryzen 9 9950X, 16 cores / 32 threads |
| RAM | 121 GiB |
| Free disk | Approximately 3.4 TiB |
| GPU | NVIDIA RTX PRO 6000 Blackwell, 97,887 MiB VRAM |
| NVIDIA driver | 595.99.02; `nvidia-smi` succeeds |
| Driver CUDA capability | 13.2 reported by `nvidia-smi`; this is not an installed CUDA toolkit version |
| Desktop | Wayland with X display `:0` |
| Git | 2.53.0, present despite the historical plan observation |
| Host Python | 3.14.4; separate Python 3.12 needed for the simulation |
| Initially missing | Docker, NVIDIA Container Toolkit, Git LFS, uv, Python 3.12, Mixar, Vulkan CLI tools |
| Privilege probe | `sudo -n true` requires interactive authentication |
| Rootless prerequisite probe | `unshare --user --map-root-user true` fails writing `uid_map`; AppArmor user-namespace restriction is enabled |

Raw commands, stdout, stderr, and exit codes are in `diagnostics/20261025T235204.379599Z/host.json`. No OS, driver, or security-policy changes were made during inspection.

## Compatibility decision

NVIDIA's [Isaac Sim 6.0 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html) list Ubuntu 22.04/24.04. The Ubuntu 26.04 host therefore needs empirical validation; a working `nvidia-smi` does not establish CUDA computation, Vulkan rendering, or physics reliability. A container changes userspace but retains the host kernel and driver.

The pinned ProtoMotions installation instructions confirm Isaac Lab revision `4ecd0b036da19ff6ad2bb4d621f886b63e9f6db8`, Isaac Sim 6.0, and Python 3.12. The upstream text contains inconsistent Isaac Lab major labels; the source revision is authoritative. No upgrade to current main branches is intended.

The official Isaac Sim 6.0.0 container checker passed twice on this host, both with exit code 0 and explicit PASS messages. It detected the NVIDIA GPU through Vulkan and accepted driver 595.99.02. The image has Ubuntu 24.04.3 userspace and Python 3.12.13. Exact digest: `nvcr.io/nvidia/isaac-sim@sha256:68735a60b6c15c85e0dd0098570c6d2cc79e928f2d068ce2790aa43284ac165d`. Evidence: `diagnostics/20261026T020033-isaac/`. This proves the official checker runs on the unchanged Ubuntu 26.04 host; it does not yet prove physics or training compatibility.

Both runs emitted Hub-startup, headless-display, power-governor, and IOMMU warnings. Raw logs are retained. No host driver, kernel, power profile, or IOMMU settings were changed.

## Installed host tooling

The user completed the host bootstrap. Docker 29.1.3 and NVIDIA Container Toolkit 1.20.1 are installed and Docker is active with the NVIDIA runtime configured. Git LFS and Vulkan tools are also installed. Fresh evidence is in `diagnostics/20261026T012503.739621Z/`.

The initial bootstrap omitted `util-linux-extra`, which supplies `sg` on this host. The user has now installed it, and `scripts/docker.sh version` successfully contacts the daemon. Exact installed package versions are recorded in `config/host-tools.json`. The repair command used was:

```bash
sudo apt-get install -y util-linux-extra
```

Alternatively, a full logout/login refreshes membership. The corrected bootstrap now includes this dependency. For a new machine with the same inspected OS (not to repeat on this installed host), the original bootstrap command is:

```bash
cd /home/vincent/Repos/DigitalHumanStudio
sudo bash scripts/install_host_tools.sh
```

This installs pinned Ubuntu Docker/Git LFS/Vulkan packages and NVIDIA Container Toolkit from NVIDIA's stable repository, configures the Docker runtime, and adds the invoking user to the Docker group (which grants host administrative capability). It does not replace the OS or NVIDIA driver. Existing container installations cause it to stop for inspection. A partial installation should be inspected before retrying. `scripts/docker.sh` can use newly assigned Docker group membership without restarting this session.

`python3 scripts/inspect_host.py` captures machine state; the latest host report is `diagnostics/20261026T013048.738346Z/host.json`. `scripts/check_isaac.sh` records the image digest and userspace, verifies GPU visibility, and runs NVIDIA's official checker twice with a five-minute limit per attempt. Once pulled, the image digest is saved in `config/isaac-image.lock` and reused. It uses the required NVIDIA license-acceptance flag for the requested installation; it does not opt into optional telemetry. It stops if userspace differs from Ubuntu 24.04, the checker exits unsuccessfully, or its explicit PASS message is missing. Earlier missing-prerequisite results are historical; the actual checker has now passed twice.

## Historical failure before the user authorized repairs

The guarded builder ran after the official checker pass. It installed build prerequisites and managed Python 3.12.13 inside Ubuntu 24.04, then failed during the documented `uv sync --python 3.12.13 --extra isaacsim` operation. The original invocation was:

```bash
python3 scripts/build_runtime.py --compatibility-evidence diagnostics/20261026T020033-isaac
```

uv 0.11.32 exited 1 because its resolution includes both `pytetwild==0.2.3` and `pytetwild[all]>=0.3.0,<0.4`. The reported branch combines `platform_machine == 'x86_64'` with membership in both `'aarch64 arm64'` and `'x86_64 AMD64'`, and includes an unrequested teleop extra. That is an impossible target-platform combination; the logs support a resolver/metadata interaction, not a conclusion that the host GPU failed.

Two bounded diagnostic dry runs used the same failed-build snapshot: first with [uv's supported-environment restriction](https://docs.astral.sh/uv/reference/settings/#environments) limited to Linux x86_64, then with that same restriction and publisher-verified uv 0.13.5. Both exited 1 with the same conflict. No source revision or dependency version requirement was changed. The ineffective configuration overlay remains in diagnostic evidence only; it was removed from the build recipe. uv 0.13.5 was a diagnostic trial, not an upgrade to the configured baseline.

Evidence is in `diagnostics/20261026T020231.007421Z-runtime-build/`: original build log and exit code, retained container metadata, original Dockerfile/install script, trial logs and exit codes, platform patch, resolver release metadata, and `stopped-result.json`. Its README identifies all retained containers and the diagnostic snapshot image. Large local source archives and caches remain under ignored `.runtime/` and `vendor/`; small diagnostic records are committed.

At this point the milestone was stopped. The user subsequently authorized the repairs described above. The original failure remains preserved; it is not evidence that reinstalling the host OS would fix the dependency-resolution problem. Do not silently change source revisions, select another backend, or begin Milestone 1.

The builder verifies two successful official checker results and their image digest before constructing the environment. The repaired recipe resolves Isaac Lab and ProtoMotions together and records the combined lock and installed environment. `scripts/check_runtime.sh` requires a final image content ID and tests GPU computation, explicit PhysX gravity/contact behavior, an RTX image, clean shutdown, and a second run. The final standalone runtime acceptance passed twice as described above.

The checker launcher retains failed containers and records their names in `retained-container.txt`. It also stops and retains the container if copying Kit logs fails, even when the checker reports PASS. Failure preservation was verified using an isolated mock Docker command. Both real successful checker containers had their logs copied before removal; no genuine failing checker was induced.

## Installed local tooling and passed authoring checks

`python3 scripts/install_local_tools.py` verifies the published SHA-256 hashes and installs Mixar 4.3.5 and uv 0.11.32 below `.runtime/`. uv installed CPython 3.12.13 in `.runtime/python/`; system Python remains 3.14.4. Repeating the installer successfully reused the verified archives and existing Python. Exact archive hashes and local Python binary hash are in the configuration records.

`scripts/check_mixar.sh` passed save, CPU image rendering, reopen in a second process, and desktop open/clean shutdown. The desktop reported an OpenGL backend using the NVIDIA RTX PRO 6000. These are authoring checks, not Isaac physics or RTX-rendering evidence. The rendered image was visually inspected and contains the expected cube.

- Logs and assertions: `diagnostics/20261025T235551-mixar/`.
- Saved project: `artifacts/milestone0/mixar-20261025T235551/milestone0.blend`.
- Render: `artifacts/milestone0/mixar-20261025T235551/mixar-preview.png`.
- Reopen interactively: `scripts/mixar.sh artifacts/milestone0/mixar-20261025T235551/milestone0.blend` from the project root.

The bundled UI emitted missing-operator/registration warnings and attempted to open its account page. Those messages are preserved in the log; no account was created or paid feature used. Basic save/reopen/desktop checks passed despite the warnings; the rest of the editor is not yet validated. Mixar created its normal user preferences under `~/.config/mixar/5.2/`.

Git history uses an explicit `Digital Human Studio bootstrap <bootstrap@localhost>` identity for the initial commit because no user Git identity was configured. No global Git configuration or remote was added.

## Repeatable commands and acceptance

From the repository root:

```bash
scripts/check_media.sh
scripts/check_runtime.sh
scripts/check_mixar.sh
scripts/mixar.sh artifacts/milestone0/mixar-20261025T235551/milestone0.blend
```

The runtime launcher uses the content ID in `config/runtime-image.lock`, runs one GPU process at a time, and requires two successful runs with process exit 0, checked scene cleanup, Kit cleanup log milestones and a pending-shutdown report from the child. It preserves failed containers. Its 900-second limit includes first-run shader compilation. Rebuilding is a separate operation:

```bash
python3 scripts/build_runtime.py --compatibility-evidence diagnostics/20261026T020033-isaac
```

The runtime command passed both complete runs on the existing host with the recorded standalone lifecycle. M0 acceptance is complete. M1 preparation is now recorded separately in [the M1 report](MILESTONE1_REPORT.md); Milestones 2–5 remain unstarted. The resolved package lock and local image content ID remain authoritative. A clean rebuild from an empty cache has not been validated; the accepted launcher reuses the installed image.

If a future runtime check demonstrates host incompatibility, a concrete supported-environment candidate is a separate Ubuntu 24.04 LTS x86_64 machine with an RTX GPU and driver meeting NVIDIA's published Isaac Sim 6.0 requirements, using the same research stack. This is a contingency recommendation only. The dependency repairs recorded above are also required on that candidate; no OS replacement, migration, or different architecture has been selected.
