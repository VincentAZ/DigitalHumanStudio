#!/opt/IsaacLab/.venv/bin/python
"""Live direction worker for the trained walking adapter (Milestone 3 live controls).

One standalone Isaac worker drives a single character and executes studio commands read
from a JSON-lines command file: ``destination``, ``stop``, ``pause``, ``reset``, ``push``,
``record`` and ``quit``. Every command is acknowledged in ``status.jsonl`` with the
simulated time, wall-clock latency and the resulting state. A fall is detected with the
same rule as training; while fallen, destination commands are rejected and only an
explicit ``reset`` restores the character at the session's spawn point. No invisible reset or teleport is used.

Commands carry an ``at`` field in simulated seconds (scripted sessions) or are applied as
soon as they are read (interactive use with an appended file or FIFO).

With ``--interactive`` the worker also publishes the latest preview frame and a state record
into ``--live-dir`` after every control step, and ``pause`` without ``wall_seconds`` freezes
simulated time until a ``resume`` command arrives. The desktop control center
(``scripts/studio_app``) appends commands to the file and reads the live directory.
"""
import argparse
import dataclasses
import hashlib
import os
import json
import math
import time
import traceback
from pathlib import Path

from protomotions.utils.simulator_imports import import_simulator_before_torch

AppLauncher = import_simulator_before_torch("isaaclab")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--controller", choices=["adapter", "tracker"], default="adapter",
                    help="adapter: GPC prior + trained walking adapter; tracker: Milestone 1 tracker following a composed clip reference")
parser.add_argument("--adapter-checkpoint", type=Path, default=None, help="inference_last.ckpt of a trained adapter (controller=adapter)")
parser.add_argument("--tracker-checkpoint", type=Path,
                    default=Path("/studio/assets/data/pretrained_models/motion_tracker/soma-bones/last_lab.ckpt"))
parser.add_argument("--walk-clip", type=int, default=30)
parser.add_argument("--stop-clip", type=int, default=30)
parser.add_argument("--idle-clip", type=int, default=30)
parser.add_argument("--prior-checkpoint", type=Path,
                    default=Path("/studio/assets/data/pretrained_models/gpc_prior/soma_bones/inference_last.ckpt"))
parser.add_argument("--commands", type=Path, required=True, help="JSON lines command file (read incrementally)")
parser.add_argument("--room-half-size", type=float, default=6.0, help="Destinations beyond this distance from the spawn are rejected")
parser.add_argument("--max-session-seconds", type=float, default=120.0)
parser.add_argument("--start-motion-id", type=int, default=7)
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--interactive", action="store_true",
                    help="Commands are applied as they arrive; pause holds until resume; preview frames are published")
parser.add_argument("--live-dir", type=Path, default=None, help="Directory receiving frame.jpg and state.json for the control center")
parser.add_argument("--preview-width", type=int, default=640)
parser.add_argument("--preview-height", type=int, default=480)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
if args.controller == "adapter" and args.adapter_checkpoint is None:
    parser.error("--adapter-checkpoint is required for --controller adapter")
args.output.mkdir(parents=True, exist_ok=True)
if args.live_dir is not None:
    args.live_dir.mkdir(parents=True, exist_ok=True)
app = AppLauncher(args).app

ARRIVAL_RADIUS = 0.3
HOLD_SPEED = 0.15
FALL_HEIGHT = 0.5
FALL_UP_Z = 0.3


def sha256_of(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run_session():
    import numpy as np
    import torch
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    from lightning.fabric import Fabric
    from isaaclab.sensors.camera import Camera, CameraCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg
    import isaaclab.sim as sim_utils
    from protomotions.utils.rotations import quat_rotate
    from protomotions.envs.mdp_component import MdpComponent
    from studio_walk import kernels
    from studio_walk.live_controllers import build_controller

    def encode(obj):
        if isinstance(obj, torch.Tensor):
            return obj.detach().cpu().tolist()
        if dataclasses.is_dataclass(obj):
            return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
        if isinstance(obj, MdpComponent):
            return obj.to_dict()
        if isinstance(obj, np.generic):
            return obj.item()
        return str(obj)

    torch.set_num_threads(4)
    Fabric.seed_everything(args.seed)
    fabric = Fabric(accelerator="gpu", devices=1, num_nodes=1, loggers=[], callbacks=[])
    fabric.launch()
    device = fabric.device
    def make_camera(_sim):
        return Camera(CameraCfg(
            prim_path="/World/StudioCamera", update_period=0, width=args.preview_width, height=args.preview_height, data_types=["rgb"],
            renderer_cfg=IsaacRtxRendererCfg(),
            spawn=sim_utils.PinholeCameraCfg(focal_length=24.0, horizontal_aperture=20.955, clipping_range=(0.1, 1000.0))))

    controller = build_controller(args.controller, args, device, fabric, app,
                                  "/studio/assets/data/motion_for_trackers/soma23_bones_seed_mini.pt", after_sim=make_camera)
    configs, robot, sim, env, camera = controller.configs, controller.robot, controller.sim, controller.env, controller.camera
    (args.output / "resolved-configs.json").write_text(json.dumps(configs, default=encode, indent=2) + "\n")
    anchor = robot.anchor_body_index
    dt = env.dt
    assert abs(dt - 1 / 30) < 1e-9
    env_ids = torch.arange(1, device=device)
    policy = controller.act

    status_stream = (args.output / "status.jsonl").open("w", buffering=1)
    trace_stream = (args.output / "trace.jsonl").open("w", buffering=1)
    writer = imageio.get_writer(str(args.output / "performance.mp4"), fps=30, codec="libx264", quality=7, macro_block_size=1)
    session = {"sim_time": 0.0, "step": 0, "frames": 0, "paused_wall_seconds": 0.0, "state": "standing",
               "fallen": False, "recording_segments": [], "active_segment": None, "spawn_xy": None,
               "destination": None, "resets": 0, "commands": [], "paused": False, "pause_started_wall": None}
    step_wall_times = []
    adapter_sha256 = controller.contract.get("adapter_sha256") or controller.contract.get("tracker_sha256")

    def heading_yaw(root_rot):
        """Facing direction: yaw of the pelvis' semantic forward axis (SOMA faces along -y)."""
        forward = quat_rotate(root_rot.unsqueeze(0), torch.tensor([[0.0, -1.0, 0.0]], device=device), w_last=True)[0]
        return math.atan2(float(forward[1]), float(forward[0]))

    def publish_live(rgb=None):
        """Atomically publish the latest state (and frame) for the control center."""
        if args.live_dir is None:
            return
        _, root_pos, root_rot, speed, up_z = current_pose()
        target = controller.target_xy()
        now = time.time()
        rate = None
        if len(step_wall_times) >= 2:
            rate = (len(step_wall_times) - 1) / max(step_wall_times[-1] - step_wall_times[0], 1e-6)
        state = {"sim_time": round(session["sim_time"], 4), "step": session["step"], "frames": session["frames"],
                 "state": session["state"], "fallen": session["fallen"], "paused": session["paused"],
                 "root_xy": [round(float(root_pos[0]), 4), round(float(root_pos[1]), 4)], "root_z": round(float(root_pos[2]), 4),
                 "yaw": round(heading_yaw(root_rot), 4), "speed": round(speed, 4), "up_z": round(up_z, 4),
                 "spawn_xy": session["spawn_xy"].tolist() if session["spawn_xy"] is not None else None,
                 "destination": session["destination"].tolist() if session["destination"] is not None else None,
                 "target_xy": [round(float(v), 4) for v in target],
                 "distance": round(float(torch.linalg.norm(target - root_pos[:2])), 4),
                 "room_half_size": args.room_half_size, "resets": session["resets"],
                 "recording": session["active_segment"]["name"] if session["active_segment"] else None,
                 "recording_segments": len(session["recording_segments"]),
                 "steps_per_wall_second": round(rate, 2) if rate else None, "wall_time": now,
                 "preview_size": [args.preview_width, args.preview_height], "adapter_sha256": adapter_sha256,
                 "controller": controller.name, "phase": controller.phase(),
                 "max_session_seconds": args.max_session_seconds}
        tmp = args.live_dir / "state.json.tmp"
        tmp.write_text(json.dumps(state) + "\n")
        os.replace(tmp, args.live_dir / "state.json")
        if rgb is not None:
            frame_tmp = args.live_dir / "frame.jpg.tmp"
            Image.fromarray(rgb).save(frame_tmp, format="JPEG", quality=85)
            os.replace(frame_tmp, args.live_dir / "frame.jpg")
    trajectory = []
    destinations = []

    def log_status(event, **fields):
        record = {"sim_time": round(session["sim_time"], 4), "step": session["step"], "wall_time": time.time(),
                  "state": session["state"], "event": event, **fields}
        status_stream.write(json.dumps(record, default=encode) + "\n")
        print("STUDIO_STATUS " + json.dumps(record, default=encode), flush=True)
        return record

    def current_pose():
        state = sim.get_robot_state()
        root_pos = state.rigid_body_pos[0, anchor]
        root_rot = state.rigid_body_rot[0, anchor]
        speed = float(torch.linalg.norm(state.rigid_body_vel[0, anchor, :2]))
        up_z = float(kernels.body_up_z(root_rot.unsqueeze(0))[0])
        return state, root_pos, root_rot, speed, up_z

    def do_reset():
        controller.reset(env_ids, args.start_motion_id)
        # The first reset samples a flat spawn; every later reset returns the character to that
        # same spot so the room, its bounds and the top-down map stay fixed for the whole session.
        pinned = session["spawn_xy"]
        original_sampler = env.terrain.sample_valid_locations
        if pinned is not None:
            env.terrain.sample_valid_locations = lambda num_envs, sample_flat=False: pinned.to(device).unsqueeze(0).repeat(num_envs, 1)
        try:
            obs, _ = env.reset(env_ids, sample_flat=True, disable_motion_resample=True)
        finally:
            env.terrain.sample_valid_locations = original_sampler
        controller.after_reset(env_ids)
        _, root_pos, _, _, _ = current_pose()
        if pinned is None:
            session["spawn_xy"] = root_pos[:2].clone()
        session["last_reset_offset_m"] = float((root_pos[:2] - session["spawn_xy"]).norm())
        session["fallen"] = False
        session["state"] = "standing"
        session["destination"] = None
        session["resets"] += 1
        env._current_context = None
        env.compute_observations(context=env._build_global_context())
        return env.get_obs()

    def in_bounds(xy):
        delta = xy - session["spawn_xy"]
        return bool(delta.abs().max() <= args.room_half_size)

    def apply_command(command, obs):
        received = time.monotonic()
        kind = command.get("cmd")
        ack = {"command": command}
        if kind == "destination":
            frame = command.get("frame", "local")
            x, y = float(command["x"]), float(command["y"])
            _, root_pos, root_rot, _, _ = current_pose()
            if frame == "local":
                facing = heading_yaw(root_rot)      # local frame: x ahead of the character, y to its left
                world = root_pos[:2] + torch.tensor([x * math.cos(facing) - y * math.sin(facing),
                                                     x * math.sin(facing) + y * math.cos(facing)], device=device)
            else:
                world = torch.tensor([x, y], device=device)
            if session["fallen"]:
                ack.update({"result": "rejected_fallen_requires_reset"})
            elif not in_bounds(world):
                ack.update({"result": "rejected_out_of_bounds", "world_xy": world.tolist(), "room_half_size": args.room_half_size})
            else:
                controller.set_destination(env_ids, world)
                session["destination"] = world.clone()
                session["state"] = "walking"
                destinations.append({"sim_time": session["sim_time"], "xy": world.tolist()})
                ack.update({"result": "accepted", "world_xy": world.tolist()})
        elif kind == "stop":
            if session["fallen"]:
                ack.update({"result": "rejected_fallen_requires_reset"})
            else:
                controller.hold(env_ids)
                _, root_pos, _, _, _ = current_pose()
                session["destination"] = root_pos[:2].clone()
                session["state"] = "stopping"
                ack.update({"result": "accepted", "hold_xy": root_pos[:2].tolist()})
        elif kind == "pause" and args.interactive and "wall_seconds" not in command:
            if session["paused"]:
                ack.update({"result": "rejected_already_paused"})
            else:
                session["state_before_pause"] = session["state"]
                session["state"] = "paused"
                session["paused"] = True
                session["pause_started_wall"] = time.monotonic()
                log_status("paused", wall_seconds=None, until="resume")
                ack.update({"result": "accepted", "sim_time_before": session["sim_time"]})
        elif kind == "resume":
            if not session["paused"]:
                ack.update({"result": "rejected_not_paused"})
            else:
                held = time.monotonic() - session["pause_started_wall"]
                session["paused_wall_seconds"] += held
                session["paused"] = False
                session["state"] = session.pop("state_before_pause", "standing")
                ack.update({"result": "accepted", "wall_seconds": held, "sim_time_after": session["sim_time"],
                            "sim_time_advanced": False})
        elif kind == "pause":
            wall = float(command.get("wall_seconds", 1.0))
            before = session["sim_time"]
            session["state_before_pause"] = session["state"]
            session["state"] = "paused"
            log_status("paused", wall_seconds=wall)
            time.sleep(wall)
            session["paused_wall_seconds"] += wall
            session["state"] = session.pop("state_before_pause")
            ack.update({"result": "accepted", "wall_seconds": wall, "sim_time_before": before,
                        "sim_time_after": session["sim_time"], "sim_time_advanced": session["sim_time"] != before})
        elif kind == "reset":
            obs = do_reset()
            ack.update({"result": "accepted", "spawn_xy": session["spawn_xy"].tolist(),
                        "respawn_offset_from_spawn_m": session["last_reset_offset_m"]})
        elif kind == "push":
            lin = torch.tensor([[float(command.get("vx", 0.0)), float(command.get("vy", 0.0)), 0.0]], device=device)
            sim._apply_root_velocity_impulse(lin, torch.zeros_like(lin), env_ids)
            ack.update({"result": "accepted", "velocity_impulse": lin[0].tolist()})
        elif kind == "record":
            action = command.get("action", "start")
            if action == "start" and session["active_segment"] is None:
                session["active_segment"] = {"start_step": session["step"], "start_sim_time": session["sim_time"], "name": command.get("name", f"segment-{len(session['recording_segments'])}")}
                ack.update({"result": "accepted"})
            elif action == "stop" and session["active_segment"] is not None:
                segment = session.pop("active_segment")
                segment.update({"end_step": session["step"], "end_sim_time": session["sim_time"]})
                session["recording_segments"].append(segment)
                session["active_segment"] = None
                ack.update({"result": "accepted", "segment": segment})
            else:
                ack.update({"result": "rejected_invalid_record_state"})
        elif kind == "quit":
            ack.update({"result": "accepted"})
        else:
            ack.update({"result": "rejected_unknown_command"})
        ack["ack_latency_ms"] = (time.monotonic() - received) * 1000.0
        session["commands"].append(log_status("command", **ack))
        return obs, kind == "quit"

    pending = []
    consumed_lines = 0

    def read_new_commands():
        nonlocal consumed_lines
        if not args.commands.exists():
            return
        lines = args.commands.read_text().splitlines()
        for line in lines[consumed_lines:]:
            if line.strip():
                pending.append(json.loads(line))
        consumed_lines = len(lines)

    (args.output / "session-contract.json").write_text(json.dumps({
        **controller.contract,
        "commands_file": str(args.commands), "room_half_size_m": args.room_half_size,
        "start_motion_id": args.start_motion_id, "control_hz": 30, "physics_hz": 120,
        "fall_rule": {"pelvis_height_below_m": FALL_HEIGHT, "up_z_below": FALL_UP_Z},
        "commands_supported": ["destination", "stop", "pause", "resume", "reset", "push", "record", "quit"],
        "interactive": args.interactive, "live_dir": str(args.live_dir) if args.live_dir else None,
        "preview_size": [args.preview_width, args.preview_height], "max_session_seconds": args.max_session_seconds,
    }, indent=2) + "\n")
    obs = do_reset()
    log_status("session_started", spawn_xy=session["spawn_xy"].tolist())
    publish_live()
    quit_requested = False
    max_steps = int(args.max_session_seconds / dt)
    with torch.no_grad():
        while not quit_requested and session["step"] < max_steps:
            read_new_commands()
            due = [c for c in pending if c.get("at", 0.0) <= session["sim_time"] + 1e-9]
            for command in due:
                pending.remove(command)
                obs, quit_requested = apply_command(command, obs)
                if quit_requested:
                    break
            if quit_requested:
                break
            if session["paused"]:
                publish_live()
                time.sleep(0.03)
                continue
            action = policy(obs, session["step"])
            obs, _, _, _, _ = env.step(action)
            session["step"] += 1
            session["sim_time"] = session["step"] * dt
            state, root_pos, root_rot, speed, up_z = current_pose()
            assert torch.isfinite(state.rigid_body_pos).all() and torch.isfinite(action).all()
            height = float(root_pos[2])
            target = controller.target_xy()
            dist = float(torch.linalg.norm(target - root_pos[:2]))
            fallen_now = (height < FALL_HEIGHT) or (up_z < FALL_UP_Z)
            if fallen_now and not session["fallen"]:
                session["fallen"] = True
                session["state"] = "fallen"
                log_status("fall_detected", pelvis_height=height, up_z=up_z,
                           note="attempt ended; evidence preserved; explicit reset required")
            elif not session["fallen"]:
                if session["destination"] is not None and dist < ARRIVAL_RADIUS and speed < HOLD_SPEED:
                    session["state"] = "standing"
                elif session["state"] in ("walking", "stopping") or (session["destination"] is not None and dist >= ARRIVAL_RADIUS):
                    session["state"] = "walking" if dist >= ARRIVAL_RADIUS else session["state"]
            trace_stream.write(json.dumps({"step": session["step"], "sim_time": round(session["sim_time"], 4),
                                           "root_pos": [round(float(v), 4) for v in root_pos], "speed": round(speed, 4),
                                           "up_z": round(up_z, 4), "target_xy": [round(float(v), 4) for v in target],
                                           "distance": round(dist, 4), "state": session["state"], "phase": controller.phase(),
                                           "dof_pos": [round(float(v), 4) for v in state.dof_pos[0]],
                                           "root_rot_xyzw": [round(float(v), 5) for v in root_rot]}) + "\n")
            trajectory.append([float(root_pos[0]), float(root_pos[1]), session["state"]])
            eye = root_pos.unsqueeze(0) + torch.tensor([[3.0, -4.0, 2.0]], device=device)
            look = root_pos.unsqueeze(0) + torch.tensor([[0.0, 0.0, 0.15]], device=device)
            camera.set_world_poses_from_view(eye, look)
            sim._sim.render()
            camera.update(dt)
            rgb = camera.data.output["rgb"].torch[0].detach().cpu().numpy()[..., :3].astype(np.uint8)
            assert rgb.shape == (args.preview_height, args.preview_width, 3) and float(rgb.std()) > 5
            writer.append_data(rgb)
            session["frames"] += 1
            step_wall_times.append(time.time())
            del step_wall_times[:-60]
            publish_live(rgb)
            if session["step"] % 300 == 0:
                Image.fromarray(rgb).save(args.output / f"frame-{session['step']:05d}.png")
    writer.close()
    status_stream.close()
    trace_stream.close()
    # top-down map of the session
    size, scale = 900, 60.0
    image = Image.new("RGB", (size, size), (248, 248, 248))
    draw = ImageDraw.Draw(image)
    spawn = session["spawn_xy"].tolist() if session["spawn_xy"] is not None else [0.0, 0.0]
    centre = size / 2

    def to_px(x, y):
        return centre + (x - spawn[0]) * scale, centre - (y - spawn[1]) * scale
    for metre in range(-7, 8):
        offset = centre + metre * scale
        colour = (200, 200, 200) if metre else (150, 150, 150)
        draw.line([(offset, 0), (offset, size)], fill=colour)
        draw.line([(0, offset), (size, offset)], fill=colour)
    half = args.room_half_size * scale
    draw.rectangle([centre - half, centre - half, centre + half, centre + half], outline=(80, 80, 80), width=2)
    colours = {"walking": (40, 140, 60), "standing": (30, 30, 200), "stopping": (200, 140, 0), "fallen": (200, 60, 60), "paused": (120, 120, 120)}
    for a, b in zip(trajectory[:-1], trajectory[1:]):
        draw.line([to_px(a[0], a[1]), to_px(b[0], b[1])], fill=colours.get(b[2], (0, 0, 0)), width=3)
    for destination in destinations:
        x, y = to_px(*destination["xy"])
        r = ARRIVAL_RADIUS * scale
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(30, 30, 200), width=2)
    draw.text((10, 10), "Live session top-down view: green walking, blue standing, orange stopping, red fallen; square = room bounds", fill=(0, 0, 0))
    image.save(args.output / "topdown.png")
    summary = {"steps": session["step"], "sim_seconds": session["sim_time"], "frames": session["frames"],
               "paused_wall_seconds": session["paused_wall_seconds"], "resets": session["resets"],
               "commands": session["commands"], "destinations": destinations,
               "recording_segments": session["recording_segments"], "final_state": session["state"],
               "interactive": args.interactive, "adapter_sha256": adapter_sha256, "controller": controller.name,
               "max_ack_latency_ms": max([c.get("ack_latency_ms", 0.0) for c in session["commands"]] + [0.0])}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, default=encode) + "\n")
    sim._sim.stage.Export(str(args.output / "final-scene.usda"))
    sim._sim.stop()
    return {"status": "checks_passed_shutdown_pending", "frames": session["frames"], "steps": session["step"],
            "commands": len(session["commands"]), "physics_hz": 120, "control_hz": 30, "training_performed": False}


exit_code = 1
try:
    result = run_session()
    from isaaclab.sim import SimulationContext
    SimulationContext.clear_instance()
    assert SimulationContext.instance() is None and app.context.get_stage() is None
    assert app.config["fast_shutdown"] is True
    result["shutdown"] = {"simulation_context_cleared": True, "stage_closed": True, "fast_shutdown": True, "skip_cleanup": False}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    exit_code = 0
except BaseException:
    traceback.print_exc()
    raise
finally:
    app.close(wait_for_replicator=True, skip_cleanup=False, exit_code=exit_code)
raise RuntimeError("Kit standalone shutdown unexpectedly returned")
