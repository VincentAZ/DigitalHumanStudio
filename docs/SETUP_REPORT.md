# Milestone 0 setup report

Status: **Milestone 0 resumed with user-authorized dependency repairs; full installation is running. Official Isaac compatibility checker and Mixar checks passed. The patched combined graph resolves; final GPU computation, physics, RTX rendering, and restart checks remain unrun.**

## Current repair — 2026-10-26 UTC

The build keeps the requested source revisions but applies explicit, hash-guarded patches to copies inside the container. The ignored vendor checkouts remain pristine. Every modification produces a unified diff and before/after hashes under `/opt/studio` for collection with the final build evidence.

- `container/configure_target.py` replaces architecture substring checks with equality alternatives and limits the universal lock to Linux x86_64, the base requirements, and the `isaacsim` extra. Unused extras are excluded from this target profile because uv otherwise resolves their unavailable optional backend packages. This preserves the selected Isaac dependency requirements.
- `container/configure_protomotions.py` lowers the MoviePy dependency floor from 2 to 1.0.3 and adds a fallback import for the 1.x image-sequence class. The combined graph selects MoviePy 1.0.3 and keeps Isaac's Pillow 12.1.1. This is a documented compatibility patch, not an unmodified upstream build; other MoviePy functionality is outside the test scope.
- ProtoMotions and `requirements_isaaclab.txt` now resolve in the Isaac Lab root project so the final environment has one combined `runtime.uv.lock`. The previous sequential installation could otherwise replace Isaac dependencies.
- Isaac Lab's original dependency overrides remain unchanged. The installed-environment audit will preserve raw `uv pip check` output and separately check default and selected-extra requirements. Only mismatches matching those explicit upstream overrides can be accepted; a Git override must match the installed commit. Such exceptions remain visible in `dependency-audit.json` and must not be described as a clean pip check.

The real combined dry run resolves 269 packages using uv 0.11.32: `diagnostics/20261026T032524Z-combined-patched-resolution/`. The first full build (`diagnostics/20261026T032701.811084Z-runtime-build/`) stopped on an NVIDIA package HTTP timeout. Its failed container and resolved lock are retained. Recovery in `diagnostics/20261026T033253Z-runtime-recovery/` reuses the downloaded cache and exact lock with `uv sync --locked`, longer HTTP timeouts and reduced download concurrency. Installation, recording encode/decode, GPU computation, PhysX contact behavior, RTX rendering, and repeatability still require actual results. No host OS, driver, simulation backend, or source revision was changed; no later milestone was started.

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

The builder verifies two successful official checker results and their image digest before constructing the environment. If installation eventually succeeds, it will preserve the upstream Isaac Lab lock before ProtoMotions installation and record the final environment freeze separately. The prepared `scripts/check_runtime.sh` requires a final image content ID and is designed to test GPU computation, explicit PhysX gravity/contact behavior, an RTX image, clean shutdown, and a repeat run. It has **not executed**. Script syntax and rejection of failed compatibility evidence passed; these are launcher checks, not runtime acceptance evidence.

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

## Acceptance evidence still required

- Actual GPU computation in the final pinned environment (container GPU visibility passed).
- Pinned Isaac Lab and ProtoMotions import/version evidence, resolved package lock, and final image digest.
- Primitive rigid-body simulation with finite poses, gravity and floor-contact assertions.
- Nonblank RTX-rendered scene saved as an image, followed by clean shutdown and a second successful run.
- Repeatable launch commands and recorded artifacts for the final installed configuration.

Milestone 0 cannot pass until these checks succeed. Milestones 1–5 remain unstarted.

If a future runtime check demonstrates host incompatibility, a concrete supported-environment candidate is a separate Ubuntu 24.04 LTS x86_64 machine with an RTX GPU and driver meeting NVIDIA's published Isaac Sim 6.0 requirements, using the same research stack. This is a contingency recommendation only. The current dependency-resolution failure must be addressed even on that candidate; no OS replacement, migration, or different architecture has been selected.
