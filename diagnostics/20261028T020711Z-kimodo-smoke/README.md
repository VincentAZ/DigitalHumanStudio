# Kimodo smoke test, 2026-10-28T02:07Z

One generation with the pinned local Kimodo-SOMA-RP-v1.2 (`config/kimodo.lock.json`), prompt
"a person waves hello with the right hand", 4 s, seed 0, 100 diffusion steps, model-default CFG
(separated [2.0, 2.0]), post-processing on. Exit 0, 20.2 s inside Kimodo (27 s including lock
verification), peak 16.4 GB GPU memory (the Llama-3-8B text encoder dominates).

Output `motion.npz`: 120 frames, 77 joints in the SOMASKEL77 order ProtoMotions expects, finite,
Y-up, metres (pelvis mean height 0.968 m, lowest joint 0.003 m). Right hand travels 3.0 m and rises
to 1.77 m; left hand travels 0.69 m: the prompt was followed.

ProtoMotions conversion (CPU, pinned runtime image): `motion.motion` with 23 bodies, 66 DOF, 120
frames at 30 fps, z-up root at 0.968 m; passed the converter's motion filter. Details: `summary.json`,
`generation.json`. Large outputs stay in `artifacts/generation/test-wave-20261028T020711Z/` (ignored).

A first attempt (20261028T020623Z) generated the same clip but failed in the wrapper's post-check
(argv handling bug in `scripts/generate_motion.py`, fixed); it was deleted and the run repeated.
