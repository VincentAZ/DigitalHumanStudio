# Milestone 1 — SOMA physical baseline

Status: **Milestone 1 complete for separate standalone workers**. [Aggregate acceptance](../diagnostics/20261026T180942Z-milestone1-acceptance/acceptance.json) passed after two full tracker runs, corrected GPC inference, and the independent trace/restart audit. Startup eligibility is recorded. Milestone 0 remains accepted for standalone workers; Milestones 2–5 remain unstarted.

## Results

| Check | Observed result | Evidence |
| --- | --- | --- |
| Physical SOMA | 23 bodies, 66 joints, exact semantic/simulator permutations | [Articulation probe](../diagnostics/20261026T173639Z-soma-articulation/) |
| Tracker, seed 0 | 61/61 successful attempts; 12,568 video frames; no reported terminations | [First run](../diagnostics/20261026T174229Z-milestone1-tracker/) |
| Tracker restart, seed 0 | 61/61 successful attempts; 12,568 frames; clean shutdown | [Second run](../diagnostics/20261026T175955Z-milestone1-tracker/) |
| GPC prior, seed 0 | 600 finite frames over 20 simulated seconds; measured contacts; process and wrapper exit 0 | [Corrected GPC run](../diagnostics/20261026T175823Z-milestone1-gpc/) |
| Physics/control | 120 Hz physics, decimation 4, 30 Hz control | Each run's `actual-simulator.json` and `resolved-configs.json` |
| Recording | 640×480 H.264 at 30 fps, one frame and state/action record per control step | Each accepted run's `media-validation.json` |

Both tracker runs produced the same upstream measurements:

| Measurement | Mean | Maximum |
| --- | ---: | ---: |
| Mean body-position error (`gt_error`, metres) | 0.071711 | 0.393663 |
| Mean body-rotation error (`gr_error`, radians) | 0.138860 | 0.449459 |
| Maximum body-position error (`max_joint_error`, metres) | 0.125880 | 0.578057 |

“Successful” uses the checkpoint's original evaluator: an attempt fails when mean body-position error exceeds 0.5 m. Rotation and maximum-body errors are reported but have no failure thresholds in that configuration. The studio also records any environment termination as an attempt failure. These are reference-tracking results, not destination-walking acceptance results. No model was trained or adapted.

All 61 bundled clips are recorded, including floor-level motions. The upstream evaluator's 600-step cap was raised to the longest runtime clip, 608 steps. The CPU inventory estimates 607 because float division rounds differently; the GPU's loaded motion lengths yield 12,568 control intervals, totaling 418.933 seconds. The runtime inventory and original per-motion frame counts are saved. No clip is silently truncated at 600 steps.

A failed/terminated attempt stays failed for scoring. Its remaining frames are retained without an invisible reset. No such failures occurred in either accepted tracker run.

## Recordings and inspection

Large files remain under ignored `artifacts/milestone1/`; diagnostic manifests record SHA-256 and byte counts.

- [Example tracker video](../artifacts/milestone1/tracker-20261026T174229Z/trial-000/performance.mp4).
- [Longest tracker clip](../artifacts/milestone1/tracker-20261026T174229Z/trial-035/performance.mp4).
- [GPC prior video](../artifacts/milestone1/gpc-20261026T175823Z/trial-000/performance.mp4).

Every trial directory contains `performance.mp4`, `trace.jsonl`, first/middle/final PNGs, and `summary.json`. Traces include timestamps, actions before/after processing, root/body world poses, joint positions and velocities, contact readings, and termination/failure flags. Names, quaternion convention and permutations are in the run contract and simulator records. Tracker output also includes upstream `upstream/results/predicted_motion_lib_epoch_0.pt` for pose replay. Replaying saved poses is authoritative; rerunning physics is a separate comparison.

Videos were checked for exact frame counts, 30 fps and image dimensions. The first run processed about 20 control frames per wall-clock second including full trace/video recording; 30 fps describes simulation-time playback, not demonstrated real-time UI throughput. Representative images were inspected, including the longest floor-level clip and the clip with the largest mean tracking error. An independent CPU trace audit checked finite values, dimensions, monotonic clocks, quaternion norms, complete sample counts, and every instantiated joint stiffness/damping/armature/effort/velocity limit against the frozen resolved configuration. Force measurements cover the four foot/toe sensors; zeros on uninstrumented bodies are not measured absence of contact.

The first tracker trace audit found maximum body speed 8.90 m/s and quaternion norm error below 2×10⁻⁷. The minimum body-origin height was −0.00623 m; body origins are not collision-surface penetration measurements. Complete per-trial ranges are retained in `trace-audit.json`.

## GPC and the preserved instrumentation failure

The GPC checkpoint loads its embedded frozen FSQ decoder and takes `max_coords_obs`. Its saved evaluator has no evaluation components, so an empty full-evaluation result would not establish a rollout. The harness instead executes 600 control steps from the bundled crouch example's initial state. This is a movement-prior smoke test, not learned crouching, goal-directed walking, or task success. The reference clip supplies reset state; the policy's inference input contains current state, not target reference poses.

The first GPC attempt (`diagnostics/20261026T175358Z-milestone1-gpc/`) recorded 600 finite frames, then failed the contact assertion: process 1, wrapper 4. Its source configuration has `robot.contact_bodies=None` and the instantiated sensor map is empty. ProtoMotions returns zero-filled force buffers for missing sensors. This was an unavailable measurement prerequisite, not evidence of zero physical contact or host incompatibility. Execution stopped; the failed container, exact commands/configuration, trace, video and logs remain preserved.

The user explicitly approved “Resume corrected validation”. The corrected harness enables only the four foot/toe measurement sensors, records this override, and verifies their presence before model inference. GPC's `observe_contacts=false` preserves the policy input. Weights, gains, physics timing, backend and source pins are unchanged. The corrected run observed maximum contact force 1,486.49 N and passed video/trace and shutdown checks. All 600 actions, joint positions and body positions matched the earlier rollout exactly; the comparison is saved in `sensor-change-comparison.json`, not generalized into a determinism guarantee.

## Pinned configuration and provenance

- Runtime image: `sha256:a233b5828caf801aabc6069c9e13169fb34fba8f365b0f72359b93e4b56055d9`.
- ProtoMotions: `f69fdcaabff31846b4d2247207417b57dc788828`.
- Isaac Lab: `4ecd0b036da19ff6ad2bb4d621f886b63e9f6db8`.
- Installed runtime: Python 3.12.13, Isaac Sim 6.0.0.1, Isaac Lab 12.0.0, ProtoMotions 3.1.0, Torch 2.11.0+cu128. The actual package lock and M0 build-copy patches remain unchanged; see [setup report](SETUP_REPORT.md).
- Physical asset: pinned `soma23_humanoid.xml`, using primitive shapes. Detailed SOMA-X 0.3.4 visual assets and skeleton transfer belong to M2.
- Tracker: recommended `motion_tracker/soma-bones/last_lab.ckpt`, its serialized inference configuration, and `soma23_bones_seed_mini.pt`.
- Prior: `gpc_prior/soma_bones/inference_last.ckpt`, its serialized inference configuration with embedded FSQ decoder, and `crouch_soma23.pt` for reset.

The [asset lock](../config/milestone1-assets.lock.json) records all 44 staged files, exact sizes, SHA-256 hashes, source URLs and legal files. Each launcher verifies every hash before inference. [CPU preflight evidence](../diagnostics/20261026T170633Z-milestone1-preflight/) records strict model loading and finite checkpoint tensors. Generated USD assets are archived separately under ignored `artifacts/milestone1/scene-assets-20261026T175358Z/`, with a [manifest](../diagnostics/20261026T175358Z-milestone1-gpc/converted-asset-manifest.json). Scene exports also retain versioned Isaac 6.0 remote HDR/MDL URLs; offline rendering from an empty cache is not established.

The [pinned tracker card](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/data/pretrained_models/motion_tracker/soma-bones/MODEL_CARD.md) recommends `last_lab.ckpt` and says its serialized configuration describes the legacy checkpoint. The harness uses the upstream inference factory to select the saved SOMA Isaac Lab settings, preserving 30 Hz control. At this exact revision, `last.ckpt` and `last_lab.ckpt` have the same committed LFS hash despite the card's separate fine-tune description. The documented filename was used; separate fine-tune identity is not independently established.

The [model licensing policy](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/legal/MODEL-LICENSING.md) keeps dataset terms separate. The user confirmed a startup below USD 1 million annual revenue for the [BONES-SEED eligibility requirement](https://bones.studio/info/seed-license). The exact statement and scope are in [the eligibility record](../config/milestone1-license.json). Initial downloads preceded that clarification; motion payloads were first loaded after confirmation. No paid service or account action was used. **Motion Data by [Bones Studio](https://bones.studio/).**

## Historical articulation probes and runtime limits

The first articulation attempt hit a read-only working directory (`20261026T171331Z-soma-articulation`). The next ran 30 finite steps but its parent rejected missing Info-level shutdown messages; its corner-of-terrain synthetic reset also produced no foot contacts (`20261026T171414Z-soma-articulation`). Both failed outcomes remain intact.

After continuation, the launcher used a writable working directory, explicit Info logging and reset (5, 5, 1.15) inside the terrain. The corrected probe (`20261026T173639Z-soma-articulation`) passed 30 finite steps, measured 351.65 N maximum contact, and exited 0 with checked cleanup.

Accepted workers explicitly clear the scene/context and use Kit's standalone cleanup lifecycle. The parent requires process exit 0 and all three shutdown log markers, plus independent media validation. M0's unresolved slow/in-process native destructor issue remains outside this accepted standalone-worker scope. Known headless/Hub, joint-importer and renderer warnings remain in full logs. No host OS, driver, architecture, package or simulator-backend changes were made.

## Repeatable commands

Run from any directory with the project path:

```bash
/home/vincent/Repos/DigitalHumanStudio/scripts/check_milestone1_preflight.sh
/home/vincent/Repos/DigitalHumanStudio/scripts/check_soma_articulation.sh
/home/vincent/Repos/DigitalHumanStudio/scripts/run_milestone1.sh tracker 0
/home/vincent/Repos/DigitalHumanStudio/scripts/run_milestone1.sh gpc 0
/home/vincent/Repos/DigitalHumanStudio/scripts/run_milestone1.sh tracker 0
```

Run sequentially and stop on a failed runtime gate. The GPU lock prevents overlapping studio jobs. Each launch saves its command, source snapshots, configurations, image/container metadata, exit codes, complete logs, per-trial summaries and artifact hashes. `scripts/audit_milestone1.py` provides the separate CPU trace/controller/restart audit. Fetching assets is separate; motion data is excluded by default unless `fetch_milestone1_assets.py --include-motion-data` is explicitly selected after eligibility is established.

The [final audit](../diagnostics/20261026T180942Z-milestone1-acceptance/trace-and-restart-audit.json) passed all three accepted runs. All 61 tracker traces were byte-identical across fresh processes; per-motion metrics and outcomes also matched exactly. This is an observation for these fixed-seed runs, not a general determinism guarantee. All 777 accepted-run artifact files were rehashed successfully. Milestone 1 is accepted; no newly acquired skill or Milestone 2 work is claimed.
