#!/opt/IsaacLab/.venv/bin/python
"""Run pinned ProtoMotions training with recorded Kit settings, a wall-clock cap and metrics.

This wrapper does not modify ProtoMotions sources. It injects the studio's Kit launch
arguments (writable portable root, log file), appends one JSON line of scalar metrics per
training epoch, and requests a clean stop (final last.ckpt save) once the wall-clock
budget is exhausted. All remaining arguments are passed to train_agent.py unchanged.
"""
import argparse
import json
import runpy
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--wall-clock-limit-seconds", type=float, required=True)
parser.add_argument("--kit-args", default="")
parser.add_argument("--metrics-log", type=Path, required=True)
parser.add_argument("--train-agent", default="/opt/ProtoMotions/protomotions/train_agent.py")
own, passthrough = parser.parse_known_args()

from isaaclab.app import AppLauncher  # noqa: E402  (simulator import must precede torch)

_original_init = AppLauncher.__init__


def _patched_init(self, launcher_args=None, **kwargs):
    if isinstance(launcher_args, dict) and own.kit_args:
        launcher_args = dict(launcher_args)
        existing = launcher_args.get("kit_args", "")
        launcher_args["kit_args"] = f"{existing} {own.kit_args}".strip()
    return _original_init(self, launcher_args, **kwargs)


AppLauncher.__init__ = _patched_init

import torch  # noqa: E402
import protomotions.agents.base_agent.agent as base_agent_module  # noqa: E402

_start = time.monotonic()
_original_post_epoch_logging = base_agent_module.BaseAgent.post_epoch_logging
own.metrics_log.parent.mkdir(parents=True, exist_ok=True)


def _scalar(value):
    if isinstance(value, torch.Tensor):
        if value.numel() != 1:
            return None
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _patched_post_epoch_logging(self, training_log_dict):
    captured = {}
    original_log_dict = self.fabric.log_dict

    def capture_log_dict(metrics, step=None):
        captured.update(metrics)
        return original_log_dict(metrics, step=step)

    self.fabric.log_dict = capture_log_dict
    try:
        _original_post_epoch_logging(self, training_log_dict)
    finally:
        del self.fabric.log_dict
    elapsed = time.monotonic() - _start
    record = {
        "epoch": int(self.current_epoch),
        "elapsed_seconds": round(elapsed, 3),
        "step_count": int(getattr(self, "step_count", 0)),
        "max_gpu_memory_gib": round(torch.cuda.max_memory_allocated() / 2 ** 30, 3)
        if torch.cuda.is_available() else None,
    }
    for key, value in {**training_log_dict, **captured}.items():
        scalar = _scalar(value)
        if scalar is not None:
            record[str(key)] = scalar
    with own.metrics_log.open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    if elapsed > own.wall_clock_limit_seconds and not self._should_stop:
        print(f"STUDIO_WALL_CLOCK_LIMIT reached after {elapsed:.0f}s at epoch {self.current_epoch}; "
              "requesting a clean stop with a final checkpoint.", flush=True)
        self._should_stop = True
    stop_request = own.metrics_log.parent / "STOP_REQUESTED"
    if stop_request.exists() and not self._should_stop:
        print(f"STUDIO_STOP_REQUESTED found after {elapsed:.0f}s at epoch {self.current_epoch}; "
              "requesting a clean stop with a final checkpoint.", flush=True)
        self._should_stop = True


base_agent_module.BaseAgent.post_epoch_logging = _patched_post_epoch_logging

sys.argv = [own.train_agent, *passthrough]
runpy.run_path(own.train_agent, run_name="__main__")
