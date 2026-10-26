"""Exercise the patched ProtoMotions MoviePy import and encode/decode real frames."""
import argparse
import ast
import importlib.metadata as metadata
import json
from pathlib import Path

import imageio_ffmpeg
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
source = Path("/opt/ProtoMotions/protomotions/simulator/base_simulator/record.py")
tree = ast.parse(source.read_text())
# Execute the actual import block from the patched source, avoiding simulator startup.
imports = [node for node in ast.walk(tree) if isinstance(node, ast.Try)
           and any(isinstance(child, ast.ImportFrom) and child.module == "moviepy"
                   for child in node.body)]
assert len(imports) == 1, "Expected the recorded MoviePy compatibility block"
namespace = {}
exec(compile(ast.Module(body=imports, type_ignores=[]), str(source), "exec"), namespace)
clip_class = namespace["ImageSequenceClip"]
frames = []
for i in range(12):
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    frame[:, :, 0 if i < 6 else 2] = 255
    frames.append(frame)
video = args.output / "recording.mp4"
clip = clip_class(frames, fps=12)
try:
    clip.write_videofile(str(video), codec="libx264", audio=False, threads=1,
                         preset="veryfast", logger=None)
finally:
    clip.close()
decoder = imageio_ffmpeg.read_frames(str(video), pix_fmt="rgb24")
info = next(decoder)
decoded = list(decoder)
assert len(decoded) == 12, len(decoded)
assert abs(info["fps"] - 12) < 0.01, info
first = np.frombuffer(decoded[0], dtype=np.uint8).reshape(64, 64, 3).mean(axis=(0, 1))
last = np.frombuffer(decoded[-1], dtype=np.uint8).reshape(64, 64, 3).mean(axis=(0, 1))
assert first[0] > 200 and first[2] < 30 and last[2] > 200 and last[0] < 30, (first, last)
(args.output / "media-result.json").write_text(json.dumps({
    "status": "passed", "frames": len(decoded), "fps": info["fps"],
    "versions": {name: metadata.version(name) for name in ("moviepy", "pillow", "numpy", "imageio-ffmpeg")},
    "import_class": f"{clip_class.__module__}.{clip_class.__name__}",
    "decoded_first_rgb_mean": first.tolist(), "decoded_last_rgb_mean": last.tolist(),
    "scope": "Actual recording import and image-sequence encode/decode; other MoviePy features untested",
}, indent=2) + "\n")
print("STUDIO_MEDIA_SMOKE_PASSED")
