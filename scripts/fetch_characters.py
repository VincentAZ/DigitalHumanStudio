#!/usr/bin/env python3
"""Prepare the studio's skinned characters from licence-checked downloads.

For every entry of config/characters.json: verify the rig file's SHA-256 against
config/character-sources.json (downloading it first when the source has a plain URL and the file is
missing), copy the licence text, then run scripts/prepare_character.py on the CPU inside the pinned
image to write .runtime/characters/<id>/ (rig.npz, textures, thumbnail.png, character.json). Finds
the project from its own location. Usage: fetch_characters.py [--id ID ...] [--force]
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / ".runtime" / "downloads"
CHARACTERS = ROOT / ".runtime" / "characters"


def sha256_of(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", action="append", default=[], help="character id(s) to prepare (default: all)")
    parser.add_argument("--force", action="store_true", help="prepare again even if the folder exists")
    args = parser.parse_args()
    sources = {s["id"]: s for s in json.loads((ROOT / "config" / "character-sources.json").read_text())["sources"]}
    wanted = json.loads((ROOT / "config" / "characters.json").read_text())["characters"]
    if args.id:
        wanted = [c for c in wanted if c["id"] in args.id]
    image = (ROOT / "config" / "runtime-image.lock").read_text().strip()
    failures = 0
    for character in wanted:
        source = sources[character["source"]]
        out = CHARACTERS / character["id"]
        if out.joinpath("character.json").exists() and not args.force:
            print(f"{character['id']}: already prepared ({out})")
            continue
        rig = DOWNLOADS / character["rig_file"]
        record = next((f for f in source.get("files", []) if f["path"] == character["rig_file"]), None)
        if not rig.exists():
            url = (record or {}).get("url") or ""
            if not url.startswith("http"):
                print(f"{character['id']}: {rig} is missing and has no direct download URL; see docs/CHARACTERS.md", file=sys.stderr)
                failures += 1
                continue
            rig.parent.mkdir(parents=True, exist_ok=True)
            print(f"{character['id']}: downloading {url}")
            with urllib.request.urlopen(url, timeout=120) as response, rig.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        digest = sha256_of(rig)
        if record and record.get("sha256") and record["sha256"] != digest:
            print(f"{character['id']}: SHA-256 mismatch for {rig} ({digest} != {record['sha256']}); refusing", file=sys.stderr)
            failures += 1
            continue
        if not record:
            print(f"{character['id']}: note: {character['rig_file']} is not hashed in config/character-sources.json (sha256 {digest})")
        out.mkdir(parents=True, exist_ok=True)
        licence = dict(source.get("licence", {}))
        text_file = licence.get("text_file")
        if text_file and (DOWNLOADS / text_file).exists():
            shutil.copy(DOWNLOADS / text_file, out / "LICENSE.txt")
            licence["text_copy"] = "LICENSE.txt"
        meta = {"name": character["name"], "description": character.get("description", ""), "licence": licence,
                "source": {"id": source["id"], "name": source.get("name"), "url": source.get("url"), "pinned": source.get("pinned")},
                "joint_map": source.get("joint_map", {}), "rig_sha256": digest}
        (out / "source.json").write_text(json.dumps(meta, indent=1) + "\n")
        command = [str(ROOT / "scripts" / "docker.sh"), "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--mount", f"type=bind,src={ROOT / 'scripts'},dst=/studio/scripts,readonly",
                   "--mount", f"type=bind,src={rig.parent},dst=/studio/rig,readonly",
                   "--mount", f"type=bind,src={out},dst=/studio/out", image,
                   "/studio/scripts/prepare_character.py", "--rig", f"/studio/rig/{rig.name}", "--out", "/studio/out", "--meta", "/studio/out/source.json", "--id", character["id"]]
        if character.get("mesh"):
            command += ["--mesh", character["mesh"]]
        if character.get("joint_name_regex"):
            command += ["--joint-name-regex", character["joint_name_regex"]]
        print(f"{character['id']}: preparing from {rig.name}")
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        (out / "prepare.log").write_text(result.stdout + result.stderr)
        if result.returncode != 0:
            print(f"{character['id']}: preparation failed (exit {result.returncode}); see {out / 'prepare.log'}", file=sys.stderr)
            print(result.stdout[-1500:] + result.stderr[-1500:], file=sys.stderr)
            failures += 1
            continue
        print(f"{character['id']}: {result.stdout.strip().splitlines()[-1]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
