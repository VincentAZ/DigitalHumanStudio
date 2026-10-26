"""Audit the combined graph, accounting only for Isaac Lab's declared overrides."""
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys
import tomllib

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

project = tomllib.loads(Path("/opt/IsaacLab/pyproject.toml").read_text())
overrides = {canonicalize_name(r.name): r for text in project["tool"]["uv"]["override-dependencies"]
             for r in [Requirement(text)]}
installed = {canonicalize_name(d.metadata["Name"]): d for d in metadata.distributions()}
environment = default_environment()
errors, exceptions = [], []
extras = {name: {""} for name in installed}
root_requirements = project["project"]["dependencies"] + project["project"]["optional-dependencies"]["isaacsim"]


def active(requirement, selected_extras):
    return requirement.marker is None or any(
        requirement.marker.evaluate(dict(environment, extra=extra)) for extra in selected_extras)


# Follow selected extras transitively; include default requirements for every distribution.
changed = True
while changed:
    changed = False
    requirements = [("project", Requirement(text), {""}) for text in root_requirements]
    requirements += [(name, Requirement(text), extras[name]) for name, dist in installed.items()
                     for text in (dist.requires or [])]
    for parent, requirement, selected in requirements:
        if not active(requirement, selected):
            continue
        name = canonicalize_name(requirement.name)
        added = requirement.extras - extras.setdefault(name, {""})
        if added:
            extras[name].update(added)
            changed = True

for parent, requirement, selected in requirements:
    if not active(requirement, selected):
        continue
    name = canonicalize_name(requirement.name)
    dist = installed.get(name)
    if dist is None:
        errors.append({"parent": parent, "requirement": str(requirement), "error": "missing"})
        continue
    if not requirement.specifier or requirement.specifier.contains(dist.version, prereleases=True):
        continue
    record = {"parent": parent, "requirement": str(requirement), "installed": dist.version}
    override = overrides.get(name)
    if override is None:
        errors.append(record)
        continue
    if override.url:
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        expected_commit = override.url.rsplit("@", 1)[1]
        allowed = direct.get("vcs_info", {}).get("commit_id") == expected_commit
        record["installed_source"] = direct
    else:
        allowed = override.specifier.contains(dist.version, prereleases=True)
    record["upstream_override"] = str(override)
    (exceptions if allowed else errors).append(record)

for name, dist in installed.items():
    requires_python = dist.metadata.get("Requires-Python")
    if requires_python and not SpecifierSet(requires_python).contains(environment["python_full_version"], prereleases=True):
        errors.append({"package": name, "requires_python": requires_python})

# Baseline constraints narrow upstream overrides and must never be waived by them.
for text in project["tool"]["uv"].get("constraint-dependencies", []):
    constraint = Requirement(text)
    dist = installed.get(canonicalize_name(constraint.name))
    if active(constraint, {""}) and (dist is None or not constraint.specifier.contains(dist.version, prereleases=True)):
        errors.append({"baseline_constraint": text, "installed": dist.version if dist else None})
for name, override in overrides.items():
    dist = installed.get(name)
    if dist is None:
        errors.append({"upstream_override": str(override), "error": "missing"})
    elif override.url:
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        if direct.get("vcs_info", {}).get("commit_id") != override.url.rsplit("@", 1)[1]:
            errors.append({"upstream_override": str(override), "installed_source": direct})
    elif not override.specifier.contains(dist.version, prereleases=True):
        errors.append({"upstream_override": str(override), "installed": dist.version})

raw = subprocess.run(["uv", "pip", "check", "--python", sys.executable],
                     text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
Path("/opt/studio/uv-pip-check.log").write_text(raw.stdout)
Path("/opt/studio/uv-pip-check.exit-code.txt").write_text(str(raw.returncode) + "\n")
report = {"status": "failed" if errors else "passed_with_declared_overrides" if exceptions else "passed",
          "errors": errors, "upstream_override_exceptions": exceptions,
          "uv_pip_check_exit_code": raw.returncode,
          "distribution_count": len(installed), "selected_extras": {k: sorted(v - {""}) for k, v in extras.items() if v != {""}}}
Path("/opt/studio/dependency-audit.json").write_text(json.dumps(report, indent=2) + "\n")
if errors or (raw.returncode != 0 and not exceptions):
    raise SystemExit("Dependency audit failed; inspect /opt/studio/dependency-audit.json and uv-pip-check.log")
print(f"Dependency audit: {report['status']}; {len(exceptions)} recorded upstream override exceptions")
