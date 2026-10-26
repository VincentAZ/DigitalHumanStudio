"""Keep Isaac's MoviePy/Pillow versions while supporting ProtoMotions recording."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import tomllib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/opt/ProtoMotions"))
    parser.add_argument("--evidence", type=Path, default=Path("/opt/studio"))
    args = parser.parse_args()
    edits = [
        ("pyproject.toml", "bea2c43f9d12ef39055511345d0e42a279753d7714e428c6cd0059383655d434",
         '"moviepy>=2,<3; python_version', '"moviepy>=1.0.3,<3; python_version'),
        ("protomotions/simulator/base_simulator/record.py",
         "a9516bc2e30975ec7b4ceefc5c659e78137440014e201cbe4461a3c022712162",
         "                    from moviepy import ImageSequenceClip\n",
         "                    try:\n"
         "                        from moviepy import ImageSequenceClip\n"
         "                    except ImportError:\n"
         "                        from moviepy.video.io.ImageSequenceClip import ImageSequenceClip\n"),
    ]
    patch, records = [], []
    for relative, expected, old, new in edits:
        path = args.source / relative
        original = path.read_text()
        if hashlib.sha256(original.encode()).hexdigest() != expected or original.count(old) != 1:
            raise RuntimeError(f"Unexpected pinned ProtoMotions source: {relative}")
        modified = original.replace(old, new)
        if relative == "pyproject.toml":
            before, after = tomllib.loads(original), tomllib.loads(modified)
            before["project"]["dependencies"] = [
                requirement.replace("moviepy>=2,<3", "moviepy>=1.0.3,<3")
                for requirement in before["project"]["dependencies"]]
            assert before == after
        patch.extend(difflib.unified_diff(original.splitlines(keepends=True),
                                         modified.splitlines(keepends=True),
                                         fromfile=f"ProtoMotions/{relative} (pinned)",
                                         tofile=f"ProtoMotions/{relative} (configured)"))
        records.append({"file": relative, "original_sha256": expected,
                        "configured_sha256": hashlib.sha256(modified.encode()).hexdigest()})
        path.write_text(modified)
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "protomotions-compatibility.patch").write_text("".join(patch))
    (args.evidence / "protomotions-compatibility.json").write_text(json.dumps({
        "reason": "Isaac Lab requires MoviePy 1.x and Pillow 12.1.1; add legacy image-sequence import",
        "requirement_change": "moviepy>=2,<3 -> moviepy>=1.0.3,<3; Lab still selects 1.x",
        "source_revision_changed": False, "files": records,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
