# Component provenance and account steps

The requested versions are in `config/baseline.json`. Null digests and locks mean unestablished, not optional. `docs/sources/manifest.json` records retrieved upstream evidence with SHA-256 hashes and failed retrievals. The pinned Isaac Lab revision did not expose a root `uv.lock` (HTTP 404); a resolved environment lock must be created during setup.

| Component | Source / version | Account or license step | Current evidence |
| --- | --- | --- | --- |
| Isaac Sim | NVIDIA NGC, 6.0.0 | NVIDIA Omniverse/Isaac terms apply; container execution uses `ACCEPT_EULA=Y`. No optional telemetry consent is set. Registry login only if public access fails. | Requested image, no validated digest yet |
| Isaac Lab | `isaac-sim/IsaacLab`, pinned Git revision | Preserve upstream BSD-3-Clause and dependency notices | Pinned project metadata retrieved; root upstream lock unavailable |
| ProtoMotions | `NVlabs/ProtoMotions`, pinned Git revision | Review repository and individual model/data licenses before asset use | Pinned installation instructions; no model assets fetched |
| Mixar | `Mixar-AI/mixar-app`, v4.3.5 Linux binary | Bundled license directory preserved; no account created or paid service used | Archive matched publisher SHA-256; basic authoring checks passed |
| uv / local Python | Astral uv 0.11.32; managed CPython 3.12.13 | Bundled license notices retained | uv archive verified against GitHub release digest; Python executable SHA-256 recorded |
| SOMA-X | Proposed 0.3.4 | Review native model license and asset-specific terms before download. Do not substitute separately licensed SMPL assets. | Not downloaded; mapping belongs to later milestones |
| Docker | Ubuntu `docker.io` package | Distribution package notices | Installation pending authentication |
| NVIDIA Container Toolkit | NVIDIA stable APT repository, 1.20.1-1 | Package notices | Installation pending authentication |

Generated smoke scenes will contain only primitives. Register every downloaded model or motion asset with its URL, revision, SHA-256, license, and local destination before later use. Do not claim asset provenance from a component's name alone.

Sources inspected on 2026-10-25:

- [Isaac Sim 6.0 requirements](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/requirements.html)
- [Isaac Sim 6.0 container procedure](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/installation/install_container.html)
- [Pinned ProtoMotions installation instructions](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/docs/source/getting_started/installation.rst)
- [NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Mixar v4.3.5 release](https://github.com/Mixar-AI/mixar-app/releases/tag/v4.3.5)
- [Mixar guest workflow](https://www.mixar.app/docs)
