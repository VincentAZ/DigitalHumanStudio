# Milestone 1 — SOMA physical baseline

Status: **started; motion trials awaiting dataset eligibility clarification**. Milestone 0 remains accepted for standalone workers. No Milestone 2–5 work has started.

## Verified preparation

Evidence: [`diagnostics/20261026T170633Z-milestone1-preflight/`](../diagnostics/20261026T170633Z-milestone1-preflight/).

- Staged 44 files from ProtoMotions revision `f69fdcaabff31846b4d2247207417b57dc788828` under ignored `.runtime/milestone1/assets/`. Every LFS payload matched its committed SHA-256 and byte count. Text and license files came from pinned Git blobs. The [asset lock](../config/milestone1-assets.lock.json) records all hashes and source URLs.
- Loaded the recommended `motion_tracker/soma-bones/last_lab.ckpt` and `gpc_prior/soma_bones/inference_last.ckpt` on CPU in the accepted image `sha256:a233b5828caf801aabc6069c9e13169fb34fba8f365b0f72359b93e4b56055d9`. Strict state loading passed with 31 and 114 model-state entries, respectively; all saved tensor values were finite.
- Both configurations agree with the bundled `soma23_humanoid.xml`: 23 bodies and 66 joint names in exact order, with 66 actions. The Isaac Lab configuration specifies 120 Hz integration, decimation 4 and 30 Hz control. Full gains, limits, solver settings and resolved configurations are in the evidence directory.
- The GPC inference configuration embeds its frozen FSQ decoder and takes `max_coords_obs`. Strict loading required no external FSQ checkpoint. This verifies model construction and loading, not behavior or task adaptation.
- Used the bundled primitive physical SOMA model. Native SOMA-X 0.3.4 visual assets have not been fetched; visual skeleton mapping belongs to Milestone 2.
- Host OS, NVIDIA driver, image, package lock and research source revisions remain unchanged. No Isaac application or GPU physics job was started for M1.

The CPU process exited 0. Its GLFW/no-display and upstream syntax warnings remain in the log. Python compilation, shell syntax and Git whitespace checks passed for project changes.

## Checkpoint provenance limitation

The [pinned tracker card](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/data/pretrained_models/motion_tracker/soma-bones/MODEL_CARD.md) recommends `last_lab.ckpt` for Isaac Lab and says its serialized configuration describes the legacy checkpoint. The configuration therefore uses the upstream inference factory to select the saved SOMA Isaac Lab parameters while preserving 30 Hz control.

At this exact revision, `last.ckpt` and `last_lab.ckpt` have the **same committed LFS object hash** (see the full recommended-checkpoint hash in the asset lock). The publisher's claimed separate fine-tune identity is not independently established. We selected the documented filename and retained this discrepancy; no alternate checkpoint or backend was substituted.

## Dataset prerequisite

Model license PDFs, notices, model cards and upstream legal notices are preserved with the assets and individually hashed. The [model licensing policy](https://github.com/NVlabs/ProtoMotions/blob/f69fdcaabff31846b4d2247207417b57dc788828/legal/MODEL-LICENSING.md) states that dataset terms remain separate.

The current [BONES-SEED license](https://bones.studio/info/seed-license) specifies eligibility for nonprofit academic institutions or commercial entities below USD 1 million annual gross revenue; other use needs a separate license. The [dataset page](https://huggingface.co/datasets/bones-studio/seed) also identifies an access agreement. The session does not establish which category covers the user's use. A clarification is pending; no paid license or account action has been taken.

The initial public GitHub fetch obtained the two bundled motion files before this eligibility issue was identified. They remain ignored local assets and have **not been loaded or executed**. The fetch script now excludes motion data by default and offers an explicit `--include-motion-data` option for use after eligibility is confirmed. Downloading a file is not evidence of license eligibility.

Motion Data by [Bones Studio](https://bones.studio/). Underlying motion data remains subject to its separate terms.

## Repeatable checks and remaining work

From any directory, using the appropriate absolute path:

```bash
/home/vincent/Repos/DigitalHumanStudio/scripts/check_milestone1_preflight.sh
```

This verifies staged hashes and reruns CPU-only asset/configuration/model checks. It does not read motion tensor payloads into a motion library or start Isaac. To fetch model and physical assets again, run `python3 /home/vincent/Repos/DigitalHumanStudio/scripts/fetch_milestone1_assets.py`; motion data is excluded by default.

After the dataset prerequisite is resolved:

1. Load the model's supported SOMA articulation in the accepted standalone Isaac process lifecycle. Verify the actual simulator body/joint permutations, gains, timestep, contacts and loaded assets against the recorded contract.
2. Run the recommended tracker on the complete bundled `soma23_bones_seed_mini.pt` trials, preserving failures, actions, physical poses, metrics and video. The upstream evaluator defaults to 600 control steps: inspect motion durations and avoid silently truncating longer trials.
3. Verify finite physical states and complete process shutdown. Repeat in a second process. Preserve and stop at any Isaac compatibility failure.
4. Exercise the GPC prior with its embedded decoder and document its distinct role. Its inference configuration has no evaluation components, so an empty `--full-eval` result would not demonstrate a successful rollout.
5. Publish the measurements, recordings, exact commands and M1 acceptance result. No milestone pass is claimed before this evidence exists.

No physical baseline score, contact validation, video, restart result or learned skill exists for M1 yet.
