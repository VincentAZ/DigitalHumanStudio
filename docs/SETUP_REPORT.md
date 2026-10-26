# Milestone 0 setup report

Status: **Milestone 0 incomplete; Docker and NVIDIA Container Toolkit installed, current-session Docker access awaiting group-refresh utility. Isaac compatibility is untested. Mixar smoke checks passed.**

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

## Resume installation

The user completed the host bootstrap. Docker 29.1.3 and NVIDIA Container Toolkit 1.20.1 are installed and Docker is active with the NVIDIA runtime configured. Git LFS and Vulkan tools are also installed. Fresh evidence is in `diagnostics/20261026T012503.739621Z/`.

The initial bootstrap omitted `util-linux-extra`, which supplies `sg` on this host. The account has Docker group membership, but the existing agent process does not. Install the missing utility in a local terminal so `scripts/docker.sh` can refresh its group:

```bash
sudo apt-get install -y util-linux-extra
```

Alternatively, a full logout/login refreshes membership. The corrected bootstrap now includes this dependency. For a new machine with the same inspected OS (not to repeat on this installed host), the original bootstrap command is:

```bash
cd /home/vincent/Repos/DigitalHumanStudio
sudo bash scripts/install_host_tools.sh
```

This installs pinned Ubuntu Docker/Git LFS/Vulkan packages and NVIDIA Container Toolkit from NVIDIA's stable repository, configures the Docker runtime, and adds the invoking user to the Docker group (which grants host administrative capability). It does not replace the OS or NVIDIA driver. Existing container installations cause it to stop for inspection. A partial installation should be inspected before retrying. `scripts/docker.sh` can use newly assigned Docker group membership without restarting this session.

Then capture `python3 scripts/inspect_host.py` and run `scripts/check_isaac.sh`. That script records the image digest and userspace, verifies GPU visibility, and runs NVIDIA's official checker twice with a five-minute limit per attempt. Once pulled, the image digest is saved in `config/isaac-image.lock` and reused. It uses the required NVIDIA license-acceptance flag for the requested installation; it does not opt into optional telemetry. It stops if userspace differs from Ubuntu 24.04, the checker exits unsuccessfully, or its explicit PASS message is missing. The launcher's prerequisite check was executed and exited 2 because Docker is absent; no Isaac process ran. Script preparation is not evidence of Isaac compatibility.

After a checker pass, remaining work is to establish the pinned Isaac Lab/ProtoMotions environment using its documented `uv sync --extra isaacsim` procedure inside Ubuntu 24.04, record the resolved lock and image digest, and run physics/render/startup/shutdown/restart checks in that final environment. Use explicit PhysX configuration where required by ProtoMotions; do not infer that a default backend proves the requested physics stack.

The checker launcher retains failed containers and records their names in `retained-container.txt`. It also stops and retains the container if copying Kit logs fails, even when the checker reports PASS. Failure preservation was verified using an isolated mock Docker command; real container behavior still requires validation after installation.

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

- Container GPU access and actual GPU computation.
- Official Isaac compatibility result with retained Kit logs.
- Pinned Isaac Lab and ProtoMotions import/version evidence, resolved package lock, and final image digest.
- Primitive rigid-body simulation with finite poses, gravity and floor-contact assertions.
- Nonblank RTX-rendered scene saved as an image, followed by clean shutdown and a second successful run.
- Repeatable launch commands and recorded artifacts for the final installed configuration.

Milestone 0 cannot pass until these checks succeed. Milestones 1–5 remain unstarted.

If Isaac fails, preserve the complete diagnostic directory and stop. A concrete supported-environment candidate would be a separate Ubuntu 24.04 LTS x86_64 machine with an RTX GPU meeting NVIDIA's requirements and a documented supported driver, using these same pinned components. This is a contingency recommendation only; no host replacement, migration, or different research architecture is selected.
