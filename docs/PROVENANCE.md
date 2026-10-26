# Component provenance and account steps

The requested versions are in `config/baseline.json`. Null digests and locks mean unestablished, not optional. `docs/sources/manifest.json` records retrieved upstream evidence with SHA-256 hashes and failed retrievals. The pinned Isaac Lab revision did not expose a root `uv.lock` (HTTP 404); the working resolved environment lock was subsequently recorded as described below.

The user authorized dependency repairs on 2026-10-26 UTC. The current build applies recorded Isaac Lab marker/profile changes and a ProtoMotions MoviePy compatibility patch to container copies of the pinned sources. These are patched builds, not pristine upstream releases. See `docs/SETUP_REPORT.md` and the emitted patch/hash manifests. The combined lock and installed artifact versions are recorded in `diagnostics/20261026T042235Z-registry-prefetched-runtime/environment/`. The final combined lock is `config/runtime.uv.lock` and the image content ID is `config/runtime-image.lock`. The final standalone launcher passes two complete physics/RTX/shutdown runs (`diagnostics/20261026T164452-runtime/`). Native slow-shutdown failures remain preserved in `diagnostics/20261026T162432Z-teardown/`. The accepted mode uses the default Kit standalone lifecycle; the package lock and image are unchanged.

| Component | Source / version | Account or license step | Current evidence |
| --- | --- | --- | --- |
| Isaac Sim | NVIDIA NGC, 6.0.0 | NVIDIA Omniverse/Isaac terms apply; container execution uses `ACCEPT_EULA=Y`. No optional telemetry consent is set. Public download required no registry login. | Digest in `config/isaac-image.lock`; official checker passed twice in `diagnostics/20261026T020033-isaac/` |
| Isaac Lab | `isaac-sim/IsaacLab`, pinned Git revision | Preserve upstream BSD-3-Clause and dependency notices | Pinned project metadata retrieved; root upstream lock unavailable |
| ProtoMotions / physical SOMA | `NVlabs/ProtoMotions`, revision `f69fdcaabff31846b4d2247207417b57dc788828` | Apache-2.0 code and upstream notices retained; model and motion terms remain separate | Physical MJCF and 44 selected asset/legal files hashed in `config/milestone1-assets.lock.json` |
| SOMA tracker / GPC prior | Recommended `last_lab.ckpt` / `inference_last.ckpt` at the same revision | NVIDIA Open Model License PDFs, notices and model cards retained with staged assets | Strict model loads, hashes and provenance discrepancy documented in `docs/MILESTONE1_REPORT.md` |
| BONES-SEED sample motions | Bundled `soma23_bones_seed_mini.pt` and `crouch_soma23.pt` | User confirmed startup below USD 1 million annual revenue; separate dataset terms and Bones Studio attribution retained | `config/milestone1-license.json`; motion assets first loaded after confirmation |
| Mixar | `Mixar-AI/mixar-app`, v4.3.5 Linux binary | Bundled license directory preserved; no account created or paid service used | Archive matched publisher SHA-256; basic authoring checks passed |
| uv / local Python | Astral uv 0.11.32; managed CPython 3.12.13 | Bundled license notices retained | uv archive verified against GitHub release digest; Python executable SHA-256 recorded |
| SOMA-X | Proposed 0.3.4 | Review native model license and asset-specific terms before download. Do not substitute separately licensed SMPL assets. | Not downloaded; mapping belongs to later milestones |
| Docker | Ubuntu `docker.io` 29.1.3-0ubuntu4.1 | Distribution package notices | Installed; daemon accessible using `scripts/docker.sh` |
| NVIDIA Container Toolkit | NVIDIA stable APT repository, 1.20.1-1 | Package notices | Installed; Docker NVIDIA runtime configured; GPU visibility and official checker passed |

Generated smoke scenes contain only primitives. Register every downloaded model or motion asset with its URL, revision, SHA-256, license, and local destination before later use. Do not claim asset provenance from a component's name alone.

The first source archive operation accidentally invoked Git LFS filters before it was interrupted. It fetched 100 small Isaac Lab test-fixture objects. Their source paths, pinned revision, SHA-256, byte counts, and license reference are recorded in `diagnostics/20261026T020145.113355Z-runtime-build/staging-interruption.json`; they remain in the ignored vendor checkout's `.git/lfs/objects/`. Subsequent source archiving explicitly skips smudging. At that M0 staging step, no character, motion-tracker, or learned-controller assets were installed. M1 assets were subsequently fetched and registered separately.

A diagnostic uv 0.13.5 binary was separately downloaded and verified against its publisher's release digest to investigate the failed dependency resolution. The trial failed with the same error and did not replace the configured uv baseline. Archive hash, release metadata, local paths, configuration changes, and retained-container records are in `diagnostics/20261026T020231.007421Z-runtime-build/`. The later repaired installation has a combined resolved lock; the diagnostic resolver did not become the baseline.

Sources inspected on 2026-10-25:

- [Isaac Sim 6.0 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html)
- [Isaac Sim 6.0 container procedure](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_container.html)
- [Pinned ProtoMotions installation instructions](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/docs/source/getting_started/installation.rst)
- [NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Mixar v4.3.5 release](https://github.com/Mixar-AI/mixar-app/releases/tag/v4.3.5)
- [Mixar guest workflow](https://www.mixar.app/docs)

## Milestone 1 asset record

The [M1 report](MILESTONE1_REPORT.md) documents model/configuration hashes, selection of the recommended Isaac Lab tracker, the embedded GPC decoder, dataset eligibility and complete run evidence. The user’s statement is preserved verbatim; no paid license, paid service or account activation occurred. Motion Data by [Bones Studio](https://bones.studio/), subject to the [BONES-SEED terms](https://bones.studio/info/seed-license). Detailed SOMA-X visual assets remain unacquired for M2. Generated physical USD files are archived and hashed; remote Isaac 6.0 renderer material/sky URLs remain in scene exports, with no claim of offline rendering from an empty cache.
