"""Scope uv's universal resolver to this project's already-selected platform."""
import difflib
import hashlib
import json
from pathlib import Path
import tomllib

project = Path("/opt/IsaacLab/pyproject.toml")
evidence = Path("/opt/studio")
original = project.read_text()
target = "sys_platform == 'linux' and platform_machine == 'x86_64'"
settings = tomllib.loads(original)["tool"]["uv"]
if "environments" in settings:
    raise RuntimeError("Existing upstream environment restriction requires review")
assert original.count("[tool.uv]\n") == 1
modified = original.replace("[tool.uv]\n", f'[tool.uv]\nenvironments = ["{target}"]\n', 1)
before = tomllib.loads(original)
after = tomllib.loads(modified)
assert after["tool"]["uv"].pop("environments") == [target]
assert before == after, "Target overlay changed more than the resolver environment"
project.write_text(modified)
(evidence / "target-environment.patch").write_text("".join(difflib.unified_diff(
    original.splitlines(keepends=True), modified.splitlines(keepends=True),
    fromfile="IsaacLab/pyproject.toml (pinned)", tofile="IsaacLab/pyproject.toml (target configuration)")))
(evidence / "target-environment.json").write_text(json.dumps({
    "environment": target,
    "original_pyproject_sha256": hashlib.sha256(original.encode()).hexdigest(),
    "configured_pyproject_sha256": hashlib.sha256(modified.encode()).hexdigest(),
    "dependency_versions_changed": False,
    "reference": "https://docs.astral.sh/uv/reference/settings/#environments"
}, indent=2) + "\n")
