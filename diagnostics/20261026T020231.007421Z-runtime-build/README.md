# Pinned runtime build failure

Outcome: **stopped, not installed, no physics/RTX/restart acceptance run**.

The separate official Isaac checker passed twice in `../20261026T020033-isaac/`. This directory records a subsequent dependency-resolution failure, not a failed host/GPU checker.

## Original build

- Command: `python3 scripts/build_runtime.py --compatibility-evidence diagnostics/20261026T020033-isaac` from the repository root.
- Docker invocation: `command.json`; complete output: `build.log`; exit status: `exit-code.txt` (1).
- Input source revisions and source-archive hashes: `source-revisions.json`. Original recipe and installer: `original-build-inputs/`.
- Local build context: `.runtime/build/20261026T020231.007421Z/` (ignored by Git).
- Failed command inside Ubuntu 24.04: `uv sync --python 3.12.13 --extra isaacsim`, using uv 0.11.32.
- Retained original container: `e721aa99631615a7bec10ed84f1eb14889d24c2f768e54a2d200531c90730bcb` (`gracious_boyd`). Metadata: `failed-container.json`; copied records: `environment-at-failure/`.

uv reports incompatible `pytetwild==0.2.3` and `pytetwild[all]>=0.3.0,<0.4` requirements in a split containing both x86_64 and ARM platform conditions. No package lock was produced and ProtoMotions installation was not reached. This evidence does not show that changing the host OS would resolve the problem.

## Diagnostic trials

The original failed container was preserved unchanged. A local snapshot was created for isolated trials:

`digital-human-studio:m0-resolver-diagnostic`, content ID `sha256:82258e8c8305bac5f3eb2c51e902fd69075ebbd6ab5ab593662b58d63e1b4100`.

| Trial | Resolver | Change in disposable copy | Result | Retained container |
| --- | --- | --- | --- | --- |
| Target restriction | 0.11.32 | Only `tool.uv.environments` restricted to Linux x86_64 | Exit 1, same conflict | `studio-resolver-target` |
| New resolver | 0.13.5 | Same target restriction, verified newer uv binary | Exit 1, same conflict | `studio-resolver-uv0135` |

Both ran `uv sync --python 3.12.13 --extra isaacsim --dry-run` in `/opt/IsaacLab` after executing `configure_target.experimental.py` with the snapshot's Python 3.12.13. The script validates that the target restriction is its only metadata change. `target-environment.patch` and JSON capture the exact modification and before/after hashes. `target-resolution.log`, `target-container.json`, `uv0135-resolution.log`, `uv0135-container.json`, and `resolver-experiments.json` preserve commands/configuration and results.

uv 0.13.5 was downloaded from the [publisher's release](https://github.com/astral-sh/uv/releases/tag/0.13.5). `uv0135-release.json` records the published SHA-256 `f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f`, which matched the downloaded archive. Its archive is `.downloads/uv-0.13.5/uv-x86_64-unknown-linux-gnu.tar.gz`; extracted files and bundled notices remain under `.runtime/tools/uv-0.13.5/`. No system tool was replaced.

The unsuccessful overlay is retained here for diagnosis and is absent from the active build recipe. The configured uv baseline remains 0.11.32. Research source revisions, dependency version requirements, host OS, NVIDIA driver, backend, and architecture were not changed. `stopped-result.json` records the stopping decision. No containers are left running from these attempts; do not remove the retained diagnostic containers or image before reviewing the failure.
