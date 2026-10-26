"""Apply the recorded platform-marker workaround to a pinned build copy only."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import tomllib

EXPECTED_SHA256 = "6b398f8c45f6b78f5e79af2c3b24089ef2aed4dac35a64bd2458dd6db69a0657"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path("/opt/IsaacLab/pyproject.toml"))
    parser.add_argument("--evidence", type=Path, default=Path("/opt/studio"))
    args = parser.parse_args()
    original = args.project.read_text()
    if hashlib.sha256(original.encode()).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Unexpected Isaac Lab metadata; review before applying the patch")
    modified = original
    for architectures, count in (("x86_64 AMD64 aarch64 arm64", 4),
                                 ("x86_64 AMD64", 4), ("aarch64 arm64", 2)):
        old = f"platform_machine in '{architectures}'"
        new = "(" + " or ".join(f"platform_machine == '{arch}'" for arch in architectures.split()) + ")"
        if modified.count(old) != count:
            raise RuntimeError(f"Unexpected marker count: {old}")
        modified = modified.replace(old, new)
    target = "sys_platform == 'linux' and platform_machine == 'x86_64'"
    modified = modified.replace("[tool.uv]\n", f'[tool.uv]\nenvironments = ["{target}"]\n', 1)
    upstream = tomllib.loads(original)
    # uv locks every optional extra, even when it is not selected for installation.
    # Preserve the requested base + isaacsim graph; do not lock unused backends.
    selected_extra = upstream["project"]["optional-dependencies"]["isaacsim"]
    modified, count = re.subn(
        r"\[project.optional-dependencies\]\n.*?(?=\[tool.isaaclab.versions\])",
        "[project.optional-dependencies]\nisaacsim = " + json.dumps(selected_extra) + "\n\n",
        modified, count=1, flags=re.DOTALL)
    assert count == 1
    modified, count = re.subn(r"^conflicts = \[\n.*?^\]\n", "conflicts = []\n",
                              modified, count=1, flags=re.DOTALL | re.MULTILINE)
    assert count == 1
    before, after = tomllib.loads(original), tomllib.loads(modified)
    # Every dependency name, extra and version constraint must remain identical.
    for section in ("dependencies",):
        assert [r.split(";")[0].strip() for r in before["project"][section]] == [
            r.split(";")[0].strip() for r in after["project"][section]]
    assert after["project"]["optional-dependencies"] == {"isaacsim": selected_extra}
    expected_settings = dict(before["tool"]["uv"], environments=[target], conflicts=[])
    assert after["tool"]["uv"] == expected_settings
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "target-metadata.patch").write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), modified.splitlines(keepends=True),
        fromfile="IsaacLab/pyproject.toml (pinned)", tofile="IsaacLab/pyproject.toml (configured)")))
    (args.evidence / "target-metadata.json").write_text(json.dumps({
        "original_sha256": EXPECTED_SHA256,
        "configured_sha256": hashlib.sha256(modified.encode()).hexdigest(),
        "target": target, "dependency_version_requirements_changed": False,
        "marker_replacements": 10,
        "profile": "base plus isaacsim; unused extras excluded from universal lock",
        "excluded_extras": sorted(set(upstream["project"]["optional-dependencies"]) - {"isaacsim"}),
        "reason": "Explicit architecture alternatives avoid uv's false substring-marker overlap",
        "isolated_test": "diagnostics/20261026T024641Z-marker-repro",
    }, indent=2) + "\n")
    args.project.write_text(modified)


if __name__ == "__main__":
    main()
