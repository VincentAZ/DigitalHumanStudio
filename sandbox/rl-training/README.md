# Sandbox: reinforcement-learning training, evaluation and comparison

Retired from the application on 2026-10-27 when the project direction changed (see `docs/DIRECTION.md`).
Nothing in `scripts/` or the control center imports this folder. It is kept so the recorded Milestone 3
evidence under `diagnostics/` and `artifacts/milestone3/` stays reproducible.

| File | Was |
|---|---|
| `studio_app/training.py`, `evaluation.py`, `compare.py` | the Training, Evaluation and Compare tabs |
| `scripts/milestone3_train.py`, `run_milestone3_train.sh` | PPO fine-tuning of the walking adapter (wall-clock cap, metrics, STOP_REQUESTED) |
| `scripts/milestone3_eval.py`, `run_milestone3_eval.sh`, `milestone3_scenarios.py` | the 100-trial reserved-scenario evaluations |
| `scripts/audit_milestone3.py`, `accept_milestone3.py`, `monitor_milestone3_training.py` | CPU audit, acceptance record, metrics trend table |
| `scripts/run_milestone3_compare.sh`, `compare_sessions.py` | the walker-versus-adapter route comparison and side-by-side video |

To run any of these again, move the pair back into `scripts/` (the launchers find the project from their
own location and expect `scripts/studio_walk` beside them) or call them with `scripts/` on `PYTHONPATH`.
The trained adapters themselves remain selectable as controllers in the live scene.
