#!/usr/bin/env python3
"""Build the pinned learning runtime only after a recorded compatibility pass."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DOCKER = str(ROOT / "scripts/docker.sh")


def output(command):
    return subprocess.check_output(command, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compatibility-evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.compatibility_evidence.resolve()
    if (evidence / "exit-code.txt").read_text().strip() != "0":
        raise RuntimeError("Compatibility run did not finish successfully")
    for attempt in (1, 2):
        if (evidence / f"check-{attempt}.exit-code.txt").read_text().strip() != "0":
            raise RuntimeError("Compatibility check failed")
        if "System checking result: PASSED" not in (evidence / f"check-{attempt}.log").read_text():
            raise RuntimeError("Official compatibility PASS evidence missing")
    image = (ROOT / "config/isaac-image.lock").read_text().strip()
    if image != (evidence / "image-digest.txt").read_text().strip():
        raise RuntimeError("Image digest differs from the tested configuration")
    if 'VERSION_ID="24.04"' not in (evidence / "container-userspace.txt").read_text():
        raise RuntimeError("Ubuntu 24.04 userspace evidence missing")

    baseline = json.loads((ROOT / "config/baseline.json").read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    context = ROOT / ".runtime/build" / stamp
    diagnostics = ROOT / "diagnostics" / f"{stamp}-runtime-build"
    context.mkdir(parents=True)
    diagnostics.mkdir(parents=True)
    locks = context / "locks"
    locks.mkdir()
    (locks / "README.txt").write_text("An established combined lock is reused with uv sync --locked.\n")
    existing_lock = ROOT / "config/runtime.uv.lock"
    if existing_lock.exists():
        shutil.copy2(existing_lock, locks / "runtime.uv.lock")
        shutil.copy2(existing_lock, diagnostics / "input-runtime.uv.lock")
    sources = {}
    for key, name, archive in (("isaac_lab", "IsaacLab", "isaaclab.tar"),
                               ("protomotions", "ProtoMotions", "protomotions.tar")):
        source = ROOT / "vendor" / name
        head = output(["git", "-C", str(source), "rev-parse", "HEAD"])
        if head != baseline[key]["revision"]:
            raise RuntimeError(f"Unexpected {name} revision: {head}")
        if output(["git", "-C", str(source), "status", "--porcelain"]):
            raise RuntimeError(f"Modified {name} source; inspect before building")
        subprocess.run(["git", "-C", str(source), "archive", "--format=tar",
                        f"--output={context / archive}", head],
                       env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="1"), check=True)
        with (context / archive).open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        sources[name] = {"revision": head, "repository": baseline[key]["repository"],
                         "archive_sha256": digest, "lfs_assets": "not_fetched"}
    uv_archive = ROOT / ".downloads/uv-x86_64-unknown-linux-gnu.tar.gz"
    with uv_archive.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != baseline["uv"]["sha256"]:
            raise RuntimeError("uv archive checksum mismatch")
    with tarfile.open(uv_archive) as bundle:
        with bundle.extractfile("uv-x86_64-unknown-linux-gnu/uv") as source, (context / "uv").open("wb") as dest:
            shutil.copyfileobj(source, dest)
    (context / "uv").chmod(0o755)
    inputs = diagnostics / "build-inputs"
    inputs.mkdir()
    for name in ("Dockerfile", "install_environment.sh", "configure_target.py", "configure_protomotions.py",
                 "verify_dependencies.py", "finish_environment.sh"):
        shutil.copy2(ROOT / "container" / name, context / name)
        shutil.copy2(ROOT / "container" / name, inputs / name)
    (context / "source-revisions.json").write_text(json.dumps(sources, indent=2) + "\n")
    shutil.copy2(context / "source-revisions.json", diagnostics / "source-revisions.json")

    tag = f"digital-human-studio:m0-{stamp.lower()}"
    command = [DOCKER, "build", "--build-arg", f"ISAAC_IMAGE={image}", "--tag", tag, str(context)]
    (diagnostics / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    print(f"Building {tag}; evidence: {diagnostics}", flush=True)
    # This host has Docker Engine without the optional Buildx plugin.
    with (diagnostics / "build.log").open("w") as log:
        result = subprocess.run(command, env=dict(os.environ, DOCKER_BUILDKIT="0"),
                                stdout=log, stderr=subprocess.STDOUT)
    (diagnostics / "exit-code.txt").write_text(str(result.returncode) + "\n")
    if result.returncode:
        raise SystemExit(f"Runtime build failed; preserve {diagnostics}")
    inspected = json.loads(output([DOCKER, "image", "inspect", tag]))
    (diagnostics / "image.json").write_text(json.dumps(inspected, indent=2) + "\n")
    image_id = inspected[0]["Id"]
    container = output([DOCKER, "create", image_id])
    try:
        subprocess.run([DOCKER, "cp", f"{container}:/opt/studio", str(diagnostics / "environment")], check=True)
    except Exception:
        (diagnostics / "retained-container.txt").write_text(container + "\n")
        raise
    else:
        subprocess.run([DOCKER, "rm", container], check=True)
    (ROOT / "config/runtime-image.lock").write_text(image_id + "\n")
    (diagnostics / "result.json").write_text(json.dumps({
        "status": "installed_not_runtime_validated", "image_id": image_id,
        "base_image": image, "tag": tag, "compatibility_evidence": str(evidence)
    }, indent=2) + "\n")
    print(f"Built {image_id}; physics/render/restart checks still required", flush=True)


if __name__ == "__main__":
    main()
