#!/usr/bin/env python3
"""Compare two recorded live sessions that ran the same route: metrics per leg, a side-by-side
video and a side-by-side top-down plot. Host-side, CPU only (JSON traces, PIL, ffmpeg).

usage: compare_sessions.py --left <session dir> --right <session dir> --out <dir> [--left-name A] [--right-name B]
Metrics follow the project's acceptance wording: arrival = pelvis within 0.3 m of the destination;
hold = 60 consecutive control steps below 0.15 m/s inside the radius; a fall is the worker's own
fall event. Nothing here changes the acceptance rules; it only makes two sessions comparable.
"""
import argparse
import json
import shutil
import statistics
import subprocess
from pathlib import Path

ARRIVAL_RADIUS, HOLD_SPEED, HOLD_STEPS = 0.3, 0.15, 60


def load_session(path: Path) -> dict:
    trace = [json.loads(line) for line in (path / "trace.jsonl").open()]
    summary = json.loads((path / "summary.json").read_text())
    status = [json.loads(line) for line in (path / "status.jsonl").open()]
    contract = json.loads((path / "session-contract.json").read_text())
    return {"path": path, "trace": trace, "summary": summary, "status": status, "contract": contract}


def leg_metrics(session: dict) -> list[dict]:
    trace, summary, status = session["trace"], session["summary"], session["status"]
    dests = [c for c in summary["commands"] if c["command"].get("cmd") == "destination" and c.get("result") == "accepted"]
    falls = [s["sim_time"] for s in status if s.get("event") == "fall_detected"]
    legs = []
    for i, d in enumerate(dests):
        t0, xy = d["sim_time"], d["world_xy"]
        t_end = dests[i + 1]["sim_time"] if i + 1 < len(dests) else trace[-1]["sim_time"]
        seg = [r for r in trace if t0 <= r["sim_time"] <= t_end]
        dist = lambda r: ((r["root_pos"][0] - xy[0]) ** 2 + (r["root_pos"][1] - xy[1]) ** 2) ** 0.5
        arrive = next((r for r in seg if dist(r) < ARRIVAL_RADIUS), None)
        hold_time, run = None, 0
        if arrive:
            for r in seg:
                if r["sim_time"] < arrive["sim_time"]:
                    continue
                run = run + 1 if (dist(r) < ARRIVAL_RADIUS and r["speed"] < HOLD_SPEED) else 0
                if run >= HOLD_STEPS:
                    hold_time = r["sim_time"]
                    break
        post = [r for r in seg if arrive and r["sim_time"] >= arrive["sim_time"] + 1.0]
        path_len = sum(((b["root_pos"][0] - a["root_pos"][0]) ** 2 + (b["root_pos"][1] - a["root_pos"][1]) ** 2) ** 0.5
                       for a, b in zip(seg[:-1], seg[1:]))
        legs.append({"leg": i, "target_xy": xy, "issued_s": t0, "window_s": round(t_end - t0, 2),
                     "arrival_s": round(arrive["sim_time"] - t0, 2) if arrive else None,
                     "hold_s": round(hold_time - t0, 2) if hold_time else None,
                     "post_arrival_median_speed": round(statistics.median(r["speed"] for r in post), 3) if post else None,
                     "post_arrival_max_distance": round(max(dist(r) for r in post), 3) if post else None,
                     "path_length_m": round(path_len, 2), "fell": any(t0 <= t <= t_end for t in falls)})
    return legs


def aggregate(legs: list[dict], session: dict) -> dict:
    arrived = [l for l in legs if l["arrival_s"] is not None]
    held = [l for l in legs if l["hold_s"] is not None]
    speeds = [l["post_arrival_median_speed"] for l in legs if l["post_arrival_median_speed"] is not None]
    return {"legs": len(legs), "arrived": len(arrived), "held_2s": len(held),
            "mean_arrival_s": round(statistics.mean(l["arrival_s"] for l in arrived), 2) if arrived else None,
            "median_post_arrival_speed": round(statistics.median(speeds), 3) if speeds else None,
            "falls": sum(1 for s in session["status"] if s.get("event") == "fall_detected"),
            "resets": session["summary"].get("resets"), "steps": session["summary"].get("steps"),
            "controller": session["contract"].get("controller"), "session": str(session["path"])}


def side_by_side_video(left: Path, right: Path, out: Path, left_name: str, right_name: str) -> bool:
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    label = lambda text: f"drawtext=fontfile={font}:text='{text}':x=16:y=16:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=8"
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(left / "performance.mp4"), "-i", str(right / "performance.mp4"),
               "-filter_complex", f"[0:v]{label(left_name)}[l];[1:v]{label(right_name)}[r];[l][r]hstack=inputs=2:shortest=1",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)]
    return subprocess.run(command).returncode == 0


def side_by_side_image(left: Path, right: Path, out: Path, left_name: str, right_name: str):
    from PIL import Image, ImageDraw
    a, b = Image.open(left / "topdown.png"), Image.open(right / "topdown.png")
    canvas = Image.new("RGB", (a.width + b.width + 20, max(a.height, b.height) + 40), (252, 252, 251))
    canvas.paste(a, (0, 40)); canvas.paste(b, (a.width + 20, 40))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 12), left_name, fill=(11, 11, 11)); draw.text((a.width + 30, 12), right_name, fill=(11, 11, 11))
    canvas.save(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--left-name", default="tracker-driven walker")
    parser.add_argument("--right-name", default="learned adapter")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sessions = {"left": load_session(args.left), "right": load_session(args.right)}
    names = {"left": args.left_name, "right": args.right_name}
    result = {"sides": {}}
    for side, session in sessions.items():
        legs = leg_metrics(session)
        result["sides"][side] = {"name": names[side], "legs": legs, "aggregate": aggregate(legs, session)}
    result["video"] = None
    if side_by_side_video(args.left, args.right, args.out / "side-by-side.mp4", args.left_name, args.right_name):
        result["video"] = "side-by-side.mp4"
    side_by_side_image(args.left, args.right, args.out / "topdowns.png", args.left_name, args.right_name)
    for side in ("left", "right"):
        shutil.copy(sessions[side]["path"] / "topdown.png", args.out / f"topdown-{side}.png")
    (args.out / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["| measure | " + " | ".join(names[s] for s in ("left", "right")) + " |", "|---|---|---|"]
    keys = [("legs", "route legs"), ("arrived", "legs arrived (≤0.3 m)"), ("held_2s", "legs with 2 s hold <0.15 m/s"),
            ("mean_arrival_s", "mean time to arrival (s)"), ("median_post_arrival_speed", "median post-arrival speed (m/s)"), ("falls", "falls")]
    for key, title in keys:
        lines.append(f"| {title} | " + " | ".join(str(result['sides'][s]['aggregate'].get(key)) for s in ("left", "right")) + " |")
    (args.out / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
