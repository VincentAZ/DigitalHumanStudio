# Project instructions

Read `IMPLEMENTATION_PLAN.md`, `PROGRESS.md`, and `docs/SETUP_REPORT.md` before changing this project.

- The current workspace is `/home/vincent/Repos/DigitalHumanStudio`. References to `LinuxHarness` in the original `PLAN.md` are historical.
- The user authorized Milestone 1 after completing Milestone 0, and on 2026-10-26 authorized Milestone 3 (destination walking) directly, with Milestone 2 (detailed character) deferred. On 2026-10-27 the user redirected the project: Milestone 3 RL tuning is stopped, and the approved plan is a director's assistant with a growing skill library (assistant panel with selectable AI providers, skill library with licence-checked shipped content, kinematic playback, objects and composition, text-to-motion generation, skinned characters). The plan lives in `docs/DIRECTION.md`. Milestone 4 as specified (trained second skill) stays unauthorized.
- Preserve the host operating system and existing NVIDIA driver. Do not reinstall the OS, change architecture, or switch simulation backends automatically.
- If an Isaac compatibility test fails, preserve commands, exit codes, logs, and configuration, then stop. Missing prerequisites are blocked tests, not proof of incompatibility.
- Keep the plan's source revisions pinned. Record actual package versions, image digests, asset hashes, provenance, and license steps. Requested versions are not a working lock.
- Do not claim a milestone passed until its completion evidence exists. Keep the progress log accurate, including unexecuted checks.
- Use one heavy GPU job at a time. Keep dependencies, caches, binaries, and large generated assets out of Git; commit small diagnostic records.
- Keep credentials out of files and logs. Do not activate paid services or expand into later applications.
- Scripts must find the project from their own location rather than rely on the caller's working directory.
