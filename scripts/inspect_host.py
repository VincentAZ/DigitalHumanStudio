#!/usr/bin/env python3
"""Capture read-only host diagnostics without dumping the process environment."""
import datetime
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROBES = {
    "os": ["cat", "/etc/os-release"],
    "kernel": ["uname", "-a"],
    "identity": ["id"],
    "cpu": ["lscpu"],
    "memory": ["free", "-h"],
    "storage": ["df", "-h", str(ROOT)],
    "gpu": ["nvidia-smi"],
    "gpu_details": ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,compute_cap", "--format=csv"],
    "git": ["git", "--version"],
    "python": ["python3", "--version"],
    "python312": ["python3.12", "--version"],
    "uv": ["uv", "--version"],
    "docker": ["docker", "version"],
    "container_toolkit": ["nvidia-container-cli", "--version"],
    "git_lfs": ["git", "lfs", "version"],
    "vulkan": ["vulkaninfo", "--summary"],
    "sudo_noninteractive": ["sudo", "-n", "true"],
    "user_namespace": ["unshare", "--user", "--map-root-user", "true"],
    "user_namespace_policy": ["cat", "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"],
}


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = ROOT / "diagnostics" / stamp
    target.mkdir(parents=True, exist_ok=False)
    report = {"timestamp_utc": stamp, "workspace": str(ROOT), "probes": {}}
    for name, command in PROBES.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            entry = {"command": command, "exit_code": result.returncode,
                     "stdout": result.stdout, "stderr": result.stderr}
        except (OSError, subprocess.TimeoutExpired) as error:
            entry = {"command": command, "exit_code": None, "error": str(error)}
        report["probes"][name] = entry
    (target / "host.json").write_text(json.dumps(report, indent=2) + "\n")
    print(target / "host.json")


if __name__ == "__main__":
    main()
