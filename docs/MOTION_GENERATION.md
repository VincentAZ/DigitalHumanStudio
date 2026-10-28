# Text-to-motion generation

Stage C of `docs/DIRECTION.md`. This note records the survey, the decision, the pinned install,
the generation command, the lock file and the smoke test. Dates are 2026-10-27 UTC unless stated.

## Survey

The studio's physics skeleton is SOMA-23 (`vendor/ProtoMotions/protomotions/robot_configs/soma23.py`);
clips enter the tracker through ProtoMotions' `.motion` format. A generator whose output is already on
the SOMA skeleton needs only a joint subselection (77 → 23), no retargeting.

| Model | Output skeleton | Training data and its licence | Code licence | Weights licence | GPU (inference) | Retarget to SOMA-23? |
| --- | --- | --- | --- | --- | --- | --- |
| **Kimodo-SOMA-RP-v1.2** (NVIDIA, 2026-10-15) — https://huggingface.co/nvidia/Kimodo-SOMA-RP-v1.2 | SOMA, 30 fps; the model predicts 30 joints and the CLI writes `somaskel77` (77 joints) | Bones Rigplay 1, proprietary 700 h mocap (not distributed); model card says "ready for commercial use" | Apache-2.0 (https://github.com/nv-tlabs/kimodo) | NVIDIA Open Model License (commercial use, derivative models allowed, no claim on outputs) | ~17 GB VRAM with the LLM2Vec text encoder on GPU; <3 GB with `TEXT_ENCODER_DEVICE=cpu` (README) | No — subselect 77 → 23 with `vendor/ProtoMotions/data/scripts/convert_soma23_npz_to_proto.py` |
| Kimodo-SOMA-RP-ArdyRep-v1.2 — https://huggingface.co/nvidia/Kimodo-SOMA-RP-ArdyRep-v1.2 | SOMA, 30 fps (ARDY motion representation, raw hips root) | as above | Apache-2.0 | NVIDIA Open Model License | as above | No |
| Kimodo-SOMA-SEED-v1.1 — https://huggingface.co/nvidia/Kimodo-SOMA-SEED-v1.1 | SOMA, 30 fps | BONES-SEED, 288 h public mocap under the Bones SEED licence (https://bones.studio/info/seed-license; this project's eligibility record is `config/milestone1-license.json`). Kimodo's README calls these models "less capable" than the Rigplay ones; v1.1 training overlapped the benchmark test split | Apache-2.0 | NVIDIA Open Model License | as above | No |
| ARDY (NVIDIA, 2026-07) — https://github.com/nv-tlabs/ardy, models `nvidia/ARDY-SOMA-RP-30FPS-*` | SOMA (and G1) | Bones Rigplay 1 | Apache-2.0 | not checked (unverified) | real-time autoregressive; VRAM not checked (unverified) | No |
| MDM (Tevet et al., 2022) — https://github.com/GuyTevet/motion-diffusion-model | HumanML3D 22-joint SMPL-based representation, 20 fps | HumanML3D: text labels over AMASS + HumanAct12 motion. AMASS cannot be redistributed and its per-dataset terms are research/non-commercial for most sources; HumanML3D is rebuilt from AMASS by script (https://github.com/EricGuo5513/HumanML3D). Commercial status of weights trained on it is unresolved (unverified) | MIT | trained checkpoints distributed by the authors; licence of the weights not separately stated (unverified) | a few GB; CLIP text encoder | Yes — SMPL-22 → SOMA-23 retargeting, no tool in this repo |
| PriorMDM (Shafir et al., 2023) — https://github.com/priorMDM/priorMDM | same as MDM | HumanML3D (as above) | MIT | as MDM (unverified) | a few GB | Yes |
| MoMask (Guo et al., CVPR 2024) — https://github.com/EricGuo5513/momask-codes | HumanML3D 22-joint, 20 fps (263-dim features) | HumanML3D, KIT-ML (KIT-ML is CC BY 4.0 per its publisher; unverified here) | MIT | checkpoints from the authors; terms not separately stated (unverified) | a few GB | Yes |
| MotionGPT (Jiang et al., NeurIPS 2023) — https://github.com/OpenMotionLab/MotionGPT | HumanML3D 22-joint | HumanML3D | MIT | T5-based checkpoints; terms not separately stated (unverified) | a few GB | Yes |
| T2M-GPT (Zhang et al., CVPR 2023) — https://github.com/Mael-zys/T2M-GPT | HumanML3D 22-joint | HumanML3D, KIT-ML | Apache-2.0 | checkpoints from the authors (unverified) | a few GB | Yes |

Code licences in the table were read from the GitHub repository licence field on 2026-10-27; the
HumanML3D/AMASS distribution statement is from the HumanML3D README ("Due to the distribution policy
of AMASS dataset, we are not allowed to distribute the data directly"). Quality claims are not
compared here: the HumanML3D family is trained on roughly 29 h of motion; Kimodo-SOMA-RP on 700 h.

### Decision: Kimodo-SOMA-RP-v1.2

- Output is already on the SOMA skeleton the studio uses; ProtoMotions ships a converter for Kimodo's
  NPZ (`convert_soma23_npz_to_proto.py`) at the pinned revision. No retargeting.
- The weights are under the NVIDIA Open Model License (commercial use permitted); the code is
  Apache-2.0; the model is not gated on Hugging Face.
- Runs locally on the studio GPU, pinned by commit (code) and revision + SHA-256 (weights).
- Caveat: Kimodo's text conditioning is LLM2Vec on Llama 3 8B Instruct (see "Text encoder"), which
  adds a 16 GB bf16 model under the Meta Llama 3 Community License.

## Text encoder (the licence step to know about)

Kimodo encodes prompts with LLM2Vec (`kimodo/model/load_model.py`): LoRA adapters
`McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp` and `...-mntp-supervised` (MIT per their model
cards, ~168 MB each) on top of the base model `meta-llama/Meta-Llama-3-8B-Instruct`. Kimodo's install
guide says the base is gated and asks for a Hugging Face token with Llama 3 access. This host has no
token and none is stored (checked: `~/.cache/huggingface/token` absent, no `HF_TOKEN`).

What was done instead: the base weights were taken from `NousResearch/Meta-Llama-3-8B-Instruct`
(revision `53346005fb0ef11d3b6a83b12c895cca40156b6c`), an ungated mirror. Its four safetensors shards
have the same SHA-256 as Meta's official repository (compared against Meta's public file metadata,
`https://huggingface.co/api/models/meta-llama/Meta-Llama-3-8B-Instruct?blobs=true`, revision
`8afb486c1db24fe5011ec46dfbe5b5dccdb575c2`):

| shard | bytes | sha256 (identical in both repos) |
| --- | --- | --- |
| model-00001-of-00004.safetensors | 4976698672 | d8cf9c4d0dd972e1a2131bfe656235ee98221679711a3beef6d46dadf0f20b5c |
| model-00002-of-00004.safetensors | 4999802720 | 8d4782b4a69ef03845159ce1a15e272aadaaf134dc138d68f616098e8531729c |
| model-00003-of-00004.safetensors | 4915916176 | 3acdd690e65c24f42a24581b8467af98bd3ca357444580f8012aacd2bd607921 |
| model-00004-of-00004.safetensors | 1168138808 | 67e9ad31c8c32abf3a55ee7fc7217b3ecb35fd3c74d98a5bd233e0e4d6964f46 |

So the weights are Meta's, and the Meta Llama 3 Community License applies regardless of the download
route (its text: `docs/licences/kimodo/LICENSE-Llama3-Community`; use of the materials constitutes
acceptance; it permits commercial use below 700 M monthly active users and requires "Built with Meta
Llama 3" attribution on redistributed derivatives). **User decision recorded as pending:** confirm the
Llama 3 licence is acceptable for the studio, or request Llama 3 access on Hugging Face and switch
`scripts/fetch_kimodo_weights.py` to the official repository. The adapter's `adapter_config.json`
is patched locally to point `base_model_name_or_path` at the local mirror directory (original hash
kept in the lock); nothing under `vendor/` is modified.

## Install (pinned)

```bash
# code
git clone https://github.com/nv-tlabs/kimodo vendor/kimodo
git -C vendor/kimodo checkout e1c219c99b4b94ba48be1fb6a1cbc64ecee4c954   # tag v1.2 + 1 commit ("remove unused tests")
# environment (uv 0.11.32, CPython 3.12.13 from .runtime/python; host Python untouched)
export UV_PYTHON_INSTALL_DIR=$PWD/.runtime/python
uv=.runtime/tools/uv-x86_64-unknown-linux-gnu/uv
$uv venv --python 3.12.13 .runtime/kimodo/venv
py=.runtime/kimodo/venv/bin/python
$uv pip install --python $py torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
$uv pip install --python $py cmake ninja               # MotionCorrection is a CMake extension; host has no cmake
PATH=$PWD/.runtime/kimodo/venv/bin:$PATH $uv pip install --python $py -e vendor/kimodo -c <nvidia pins>
# weights (no token), lock file and licence copies
$py scripts/fetch_kimodo_weights.py
```

`<nvidia pins>` is the `==` lines of `vendor/kimodo/docker_requirements.txt` (NVIDIA's own uv lock
for Python 3.10, used here as constraints so transformers 5.1.0, peft 0.18.1, numpy 1.26.4 etc. match
what Kimodo was tested with). The resolved environment is `config/kimodo-requirements.lock.txt`
(`uv pip freeze`). PyTorch 2.9.1+cu128 was chosen because it ships sm_120 (Blackwell) kernels; Kimodo
only requires PyTorch >= 2.0.

## Generate

```bash
python3 scripts/generate_motion.py --prompt "a person waves hello with the right hand" \
    --seconds 4 --seed 0 --output artifacts/generation/<name>
# options: --steps 100  --cfg-weight W (regular CFG; default is the model's separated [2.0, 2.0])  --device cuda|cuda:N|cpu
```

The script finds the project from its own location, verifies every file in `config/kimodo.lock.json`
by size and SHA-256 and the `vendor/kimodo` commit, takes `.runtime/studio-gpu.lock` and refuses if a
`studio-*` container is running, then runs `kimodo.scripts.generate` inside the venv with
`CHECKPOINT_DIR`, `TEXT_ENCODERS_DIR`, `TEXT_ENCODER_MODE=local` and `HF_HUB_OFFLINE=1` (no network).
Outputs: `motion.npz`, `generation.json`, `generate.log`. It checks the NPZ has `posed_joints`
`[T, 77, 3]` and `local_rot_mats` `[T, 77, 3, 3]` with finite values, and that Kimodo's
`SOMASkeleton77` joint order equals the list stored in the lock, which was copied from
`SOMASKEL77_BONE_NAMES` in ProtoMotions' converter (77/77 names identical, checked 2026-10-27).

NPZ layout (Kimodo README): `posed_joints [T,J,3]` global joint positions, `global_rot_mats`
`[T,J,3,3]`, `local_rot_mats [T,J,3,3]` parent-relative, `foot_contacts [T,4]`, `smooth_root_pos [T,3]`,
`root_positions [T,3]`, `global_root_heading [T,2]`; J = 77, 30 fps, joint 0 = Hips. Axes and units are
reported in the smoke test below.

Convert to the studio's SOMA-23 `.motion` (CPU, pinned runtime image, no GPU):

```bash
image=$(cat config/runtime-image.lock)
scripts/docker.sh run --rm --user "$(id -u):$(id -g)" --env PYTHONPATH=/studio/ProtoMotions/data/scripts \
  --mount type=bind,src=$PWD/vendor/ProtoMotions,dst=/studio/ProtoMotions,readonly \
  --mount type=bind,src=$PWD/<npz dir>,dst=/studio/in --mount type=bind,src=$PWD/<out dir>,dst=/studio/out \
  --workdir /studio/ProtoMotions "$image" data/scripts/convert_soma23_npz_to_proto.py \
  --input-dir /studio/in --output-dir /studio/out --input-fps 30 --output-fps 30
```

## Lock file

`config/kimodo.lock.json`: code repo + commit, each weight repo id + revision + licence (+ licence file
SHA-256), every file's bytes and SHA-256, the adapter patch record, the 77 joint names, the download
date. Licence texts: `docs/licences/kimodo/` (NVIDIA Open Model License, the model card, the Llama 3
Community License).

## Smoke test (2026-10-28T02:07Z, `diagnostics/20261028T020711Z-kimodo-smoke/`)

Prompt "a person waves hello with the right hand", 4 s, seed 0, 100 steps, model-default CFG
(separated [2.0, 2.0]), post-processing on. Exit 0. Kimodo wall clock 20.2 s (27 s with lock
verification of 17 GB); peak GPU memory 16.4 GB allocated on the RTX PRO 6000 Blackwell (torch
2.9.1+cu128); the text encoder dominates, `TEXT_ENCODER_DEVICE=cpu` would bring it under 3 GB.

- `motion.npz` (826 KB, sha256 `5f2c2abc…`): `posed_joints [120, 77, 3]`, `local_rot_mats` and
  `global_rot_mats [120, 77, 3, 3]`, `root_positions`/`smooth_root_pos [120, 3]`,
  `global_root_heading [120, 2]`, `foot_contacts [120, 6]` (bool; the README says 4 columns), plus an
  undocumented `posed_joints_norootpos [120, 30, 3]`. All finite; rotation matrices orthonormal to 1e-6.
- Axes and units: **Y up, metres**. Pelvis (joint 0, `Hips`) mean (x, y, z) = (-0.001, 0.968, -0.005)
  m; lowest joint over the clip 0.003 m (toes on the y = 0 floor); head top at 1.56 m. The SOMA rest
  pelvis is about 0.95 m, so the height is plausible.
- Joint order: the runner reports Kimodo's `SOMASkeleton77` names and the script compares them with
  the 77 names in the lock (copied from ProtoMotions' `SOMASKEL77_BONE_NAMES`); identical.
- Content: right hand path length 3.01 m, rising from 0.83 m to 1.77 m; left hand 0.69 m; feet
  planted (all contact flags true). The prompt was followed.
- Conversion to SOMA-23 in the pinned runtime image (CPU, 2.5 s, exit 0, motion filter passed):
  `proto/motion.motion` (260 KB, sha256 `d95cbd10…`) with `fps 30`, `dof_pos [120, 66]`,
  `dof_vel [120, 66]`, `rigid_body_pos [120, 23, 3]`, `rigid_body_rot [120, 23, 4]`,
  `rigid_body_vel`, `rigid_body_ang_vel [120, 23, 3]`, `rigid_body_contacts [120, 23]`,
  `local_rigid_body_rot [120, 23, 4]`. The converter rotates to z-up: root mean (0.001, -0.005,
  0.968) m, lowest body 0.02 m.

Expected log noise: transformers prints UNEXPECTED/MISSING LoRA weight tables while LLM2Vec loads
(Kimodo's quick-start says to ignore them) and peft warns about a second `peft_config`; both are
upstream behaviour at the pinned versions.

## Not verified

- Kimodo-SOMA-SEED, ARDY and the HumanML3D-family weights were not downloaded or run; their rows in
  the survey are from their READMEs and repository metadata only.
- The Bones SEED licence text could not be fetched here (the dataset is gated); the project's
  existing eligibility record is used.
- Only one prompt and seed were generated; quality across prompts, `--cfg-weight` and `--steps`
  variations, and tracker follow error on the converted clip are open.

## Studio integration (text to skill)

`scripts/generate_skill.sh --prompt "..." [--seconds 4] [--seed 0] [--name skill_id]` is the one
command the studio uses: it runs `scripts/generate_motion.py` (the pinned venv and weights above),
then `scripts/import_skill.sh`, which converts the 77-joint npz with ProtoMotions' own
`create_motion_from_soma23_data` on the CPU inside the pinned image, trims still frames at both ends
(a frame counts as still when no body moves faster than 0.25 m/s), writes `skills/<id>/motion.pt`,
`skill.json` (measured duration, entry and exit pose, travel; licence: NVIDIA Open Model License
for the model, the clip belongs to the user; provenance: prompt, seed, frames, model repo and
revision, weights hash, text encoder repos, diffusion steps, guidance, Kimodo commit, torch, GPU)
and the stick-figure previews, and records the run under `diagnostics/<stamp>-generate-<id>/`.
The same pipeline backs the control center's "Create a skill" dialog (bridge `generateSkill`, a
background tool worker) and the assistant's `generate_skill` tool. A generated skill plays like any
clip: exactly in kinematic playback, through the tracker in a physical session.

First generated skills (2026-10-28): `wave_hello` ("a person waves hello with the right hand", 4 s),
`bow_politely` ("a person bows politely with the hands together", 4 s, made from the dialog) and
`robot_dance` ("a person dances like a robot", 6 s); each took about 30 s wall clock, of which the
diffusion itself is 1.2 s and the rest is loading the 17 GB of weights. `--trim-still` initially
used the pelvis speed and cut the wave to 11 frames; it now uses the fastest body.
