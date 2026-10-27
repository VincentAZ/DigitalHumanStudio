#!/opt/IsaacLab/.venv/bin/python
"""Reserved-scenario acceptance evaluation for Milestone 3 destination walking.

Runs one scenario set (flat, redirect or push) from config/milestone3-scenarios.json with
either the trained walking adapter or the unadapted GPC prior in the same task
environment. Every trial records the pelvis trajectory, speed, distance to the current
destination, upright axis and foot contact forces; the acceptance rule is scored
afterwards from the saved data and can be re-checked on the CPU.

Batch mode scores every selected trial in parallel (one environment per trial).
Record mode runs trials one at a time with an RTX follow camera and saves video.
"""
import argparse
import dataclasses
import hashlib
import json
import math
import time
import traceback
from pathlib import Path

from protomotions.utils.simulator_imports import import_simulator_before_torch

AppLauncher = import_simulator_before_torch("isaaclab")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--controller", choices=["adapter", "prior"], required=True)
parser.add_argument("--adapter-checkpoint", type=Path, default=None,
                    help="PEFT inference_last.ckpt; its directory must hold resolved_configs_inference.pt")
parser.add_argument("--env-config", type=Path, default=None,
                    help="resolved_configs_inference.pt defining the task environment (defaults to the adapter's)")
parser.add_argument("--prior-checkpoint", type=Path,
                    default=Path("/studio/assets/data/pretrained_models/gpc_prior/soma_bones/inference_last.ckpt"))
parser.add_argument("--scenarios", type=Path, default=Path("/studio/scenarios.json"))
parser.add_argument("--set", dest="scenario_set", choices=["flat", "redirect", "push"], required=True)
parser.add_argument("--trial-ids", default="all", help="'all', 'a-b' or comma separated ids")
parser.add_argument("--record", action="store_true", help="Sequential single-environment trials with video")
parser.add_argument("--seed", type=int, default=0)
parser.add_argument("--scenario-friction", type=int, default=1,
                    help="1 applies each trial's robot contact friction value; 0 keeps the simulator default")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
app = AppLauncher(args).app

ARRIVAL_RADIUS = 0.3
LOOSE_RADIUS = 0.5
DEADLINE_S = 15.0
HOLD_SPEED = 0.15
HOLD_S = 2.0
FALL_HEIGHT = 0.5
FALL_UP_Z = 0.3


def select_trial_ids(spec, count):
    if spec == "all":
        return list(range(count))
    if "-" in spec and "," not in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",") if x]


def sha256_of(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run_evaluation():
    import numpy as np
    import torch
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw
    from tensordict import TensorDict
    from lightning.fabric import Fabric
    from isaaclab.sensors.camera import Camera, CameraCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg
    import isaaclab.sim as sim_utils
    import warp as wp
    from protomotions.simulator.base_simulator.utils import convert_friction_for_simulator
    from protomotions.utils.component_builder import build_all_components
    from protomotions.utils.hydra_replacement import get_class
    from protomotions.utils.rotations import calc_heading, calc_heading_quat, quat_rotate
    from protomotions.envs.mdp_component import MdpComponent
    from protomotions.agents.common.config import PretrainedModelConfig
    from protomotions.agents.common.pretrained import load_pretrained_model_module
    from studio_walk import kernels
    from studio_walk.control import ScriptedTargetCommandSource
    from studio_walk.experiment_common import apply_studio_inference_overrides

    def encode(obj):
        if isinstance(obj, torch.Tensor):
            return obj.detach().cpu().tolist()
        if dataclasses.is_dataclass(obj):
            return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
        if isinstance(obj, MdpComponent):
            return obj.to_dict()
        if isinstance(obj, (np.generic,)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    def save(name, value):
        (args.output / name).write_text(json.dumps(value, default=encode, indent=2, allow_nan=False) + "\n")

    torch.set_num_threads(4)
    Fabric.seed_everything(args.seed)
    fabric = Fabric(accelerator="gpu", devices=1, num_nodes=1, loggers=[], callbacks=[])
    fabric.launch()
    device = fabric.device

    scenarios = json.loads(args.scenarios.read_text())
    trials_all = scenarios["sets"][args.scenario_set]
    trial_ids = select_trial_ids(args.trial_ids, len(trials_all))
    trials = [trials_all[i] for i in trial_ids]
    assert all(t["id"] == i for t, i in zip(trials, trial_ids))
    num_envs = 1 if args.record else len(trials)

    env_config_path = args.env_config
    if env_config_path is None:
        assert args.adapter_checkpoint is not None, "--env-config or --adapter-checkpoint is required"
        env_config_path = args.adapter_checkpoint.parent / "resolved_configs_inference.pt"
    configs = torch.load(env_config_path, map_location="cpu", weights_only=False)
    robot, sim_cfg, env_cfg = configs["robot"], configs["simulator"], configs["env"]
    apply_studio_inference_overrides(env_cfg)
    sim_cfg.num_envs, sim_cfg.headless, sim_cfg.w_last = num_envs, True, True
    assert sim_cfg.sim.fps == 120 and sim_cfg.sim.decimation == 4
    configs["motion_lib"].motion_file = "/studio/assets/data/motion_for_trackers/soma23_bones_seed_mini.pt"
    configs["motion_lib"].motion_file_shard_indices = None
    assert configs["scene_lib"].scene_file is None
    if "pretrained_modules" in dir(configs["agent"]) and "prior" in configs["agent"].pretrained_modules:
        configs["agent"].pretrained_modules["prior"].checkpoint_path = str(args.prior_checkpoint)
    terrain_cfg, sim_cfg = convert_friction_for_simulator(configs["terrain"], sim_cfg)
    configs["terrain"], configs["simulator"] = terrain_cfg, sim_cfg
    save("resolved-configs.json", configs)

    components = build_all_components(terrain_cfg, configs["scene_lib"], configs["motion_lib"],
                                      sim_cfg, robot, device, simulation_app=app)
    sim = components["simulator"]
    camera = None
    if args.record:
        camera = Camera(CameraCfg(
            prim_path="/World/StudioCamera", update_period=0, width=640, height=480,
            data_types=["rgb"], renderer_cfg=IsaacRtxRendererCfg(),
            spawn=sim_utils.PinholeCameraCfg(focal_length=24.0, horizontal_aperture=20.955,
                                           clipping_range=(0.1, 1000.0))))
    env = get_class(env_cfg._target_)(config=env_cfg, robot_config=robot, device=device,
                                      terrain=components["terrain"], scene_lib=components["scene_lib"],
                                      motion_lib=components["motion_lib"], simulator=sim)
    source = env.control_manager.components["target"].command_source
    assert isinstance(source, ScriptedTargetCommandSource)
    anchor = robot.anchor_body_index
    assert abs(env.dt - 1 / 30) < 1e-9
    dt = env.dt
    env_ids = torch.arange(num_envs, device=device)
    ordering = sim._get_sim_body_ordering()
    foot_names = ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
    semantic_names = robot.kinematic_info.body_names
    foot_ids = torch.tensor([semantic_names.index(n) for n in foot_names], device=device)
    assert set(sim._contact_sensor_map) == set(foot_names), sim._contact_sensor_map

    # ---- controller ----
    controller_record = {"controller": args.controller, "prior_checkpoint": str(args.prior_checkpoint),
                         "prior_sha256": sha256_of(args.prior_checkpoint)}
    if args.controller == "adapter":
        ckpt = args.adapter_checkpoint
        controller_record.update({"adapter_checkpoint": str(ckpt), "adapter_sha256": sha256_of(ckpt),
                                  "env_config": str(env_config_path), "env_config_sha256": sha256_of(env_config_path)})
        agent = get_class(configs["agent"]._target_)(config=configs["agent"], env=env, fabric=fabric,
                                                   root_dir=args.output / "upstream")
        agent.setup()
        agent.load(ckpt, load_env=False, load_training_state=False)
        agent.eval()
        actor = agent.model._actor
        controller_record["actor_in_keys"] = list(actor.in_keys)
        controller_record["peft"] = {"type": configs["agent"].model.actor.peft.peft_type,
                                     "rank": configs["agent"].model.actor.peft.rank,
                                     "sampling_mode": configs["agent"].model.actor.peft.sampling_mode}

        def policy(obs, step):
            agent.pre_collect_step(step)
            td = agent.obs_dict_to_tensordict(agent.add_agent_info_to_obs(obs))
            out = agent.model(td)
            return out["mean_action"] if "mean_action" in out.keys() else out["action"]

        def policy_reset(ids):
            if hasattr(agent.model, "reset_rollout_context"):
                agent.model.reset_rollout_context(env_ids=ids)
    else:
        prior = load_pretrained_model_module(
            PretrainedModelConfig(checkpoint_path=str(args.prior_checkpoint), module_path=""),
            device=device, prefer_inference_config=True)
        prior.eval()
        prior_keys = prior.get_inference_in_keys()
        controller_record["prior_inference_keys"] = list(prior_keys)
        assert prior_keys == ["max_coords_obs"], prior_keys
        if hasattr(prior, "reset_rollout_context"):
            prior.reset_rollout_context(num_envs=num_envs, device=device)

        def policy(obs, step):
            td = TensorDict({k: obs[k] for k in prior_keys}, batch_size=num_envs, device=device)
            with torch.no_grad():
                return prior.act(td)["action"]

        def policy_reset(ids):
            if hasattr(prior, "reset_rollout_context"):
                prior.reset_rollout_context(env_ids=ids)

    # ---- friction control ----
    def apply_friction(values):
        materials = wp.to_torch(sim._robot.root_view.get_material_properties()).clone()
        friction = torch.as_tensor(values, device=materials.device, dtype=materials.dtype)
        materials[:, :, 0] = friction.unsqueeze(-1)
        materials[:, :, 1] = friction.unsqueeze(-1)
        sim._robot.root_view.set_material_properties(
            wp.from_torch(materials, dtype=wp.float32),
            wp.from_torch(torch.arange(num_envs, dtype=torch.int), dtype=wp.int32))
        readback = wp.to_torch(sim._robot.root_view.get_material_properties())
        assert torch.allclose(readback[:, :, 0].float(), friction.float().unsqueeze(-1), atol=1e-5)

    motion_lengths = env.motion_lib.get_motion_length(None)
    hold_steps = int(round(HOLD_S / dt))
    deadline_steps = int(round(DEADLINE_S / dt))
    margin_steps = int(round(3.0 / dt))
    scenario_hash = sha256_of(args.scenarios)
    save("run-contract.json", {
        **controller_record, "scenario_set": args.scenario_set, "scenario_file": str(args.scenarios),
        "scenario_sha256": scenario_hash, "trial_ids": trial_ids, "num_envs": num_envs, "record": args.record,
        "seed": args.seed, "physics_hz": 120, "control_hz": 30,
        "acceptance": {"arrival_radius_m": ARRIVAL_RADIUS, "deadline_s": DEADLINE_S, "hold_speed_mps": HOLD_SPEED,
                       "hold_s": HOLD_S, "loose_radius_m": LOOSE_RADIUS, "fall_height_m": FALL_HEIGHT,
                       "fall_up_z": FALL_UP_Z},
        "scenario_friction_applied": bool(args.scenario_friction),
        "semantic_body_names": semantic_names, "sim_body_names": ordering.body_names,
        "contact_sensors": list(sim._contact_sensor_map), "training_performed": False})
    sim._sim.stage.Export(str(args.output / "initial-scene.usda"))

    def start_batch(batch):
        ids = torch.tensor([t["start_motion_id"] for t in batch], device=device, dtype=torch.long)
        phases = torch.tensor([t["start_phase"] for t in batch], device=device)
        env.motion_manager.motion_ids[:] = ids
        env.motion_manager.motion_times[:] = phases * motion_lengths[ids]
        env.reset(env_ids, sample_flat=True, disable_motion_resample=True)
        if args.scenario_friction:
            apply_friction([t["friction"] for t in batch])
        policy_reset(env_ids)
        state = sim.get_robot_state()
        root_pos = state.rigid_body_pos[:, anchor]
        root_rot = state.rigid_body_rot[:, anchor]
        heading_q = calc_heading_quat(root_rot, w_last=True)
        heading = calc_heading(root_rot, True)

        def heading_offset(dist, bearing_deg):
            local = torch.zeros(len(batch), 3, device=device)
            local[:, 0] = dist * torch.cos(torch.deg2rad(bearing_deg))
            local[:, 1] = dist * torch.sin(torch.deg2rad(bearing_deg))
            return quat_rotate(heading_q, local, w_last=True)[:, :2]

        dist1 = torch.tensor([t["distance_m"] for t in batch], device=device)
        bear1 = torch.tensor([t["bearing_deg"] for t in batch], device=device)
        first = root_pos[:, :2] + heading_offset(dist1, bear1)
        source.set_target_now(env_ids, first)
        second = None
        change_steps = None
        if args.scenario_set == "redirect":
            dist2 = torch.tensor([t["second_distance_m"] for t in batch], device=device)
            bear2 = torch.tensor([t["second_bearing_deg"] for t in batch], device=device)
            second = first + heading_offset(dist2, bear2)
            change_time = torch.tensor([t["change_time_s"] for t in batch], device=device)
            source.schedule(env_ids, 0, change_time, second)
            change_steps = torch.round(change_time / dt).long()
        env._current_context = None
        env.compute_observations(context=env._build_global_context())
        obs = env.get_obs()
        assert torch.allclose(env.control_manager.components["target"]._tar_pos[:, :2], first)
        return obs, {"start_xy": root_pos[:, :2].clone(), "start_z": root_pos[:, 2].clone(),
                     "heading_rad": heading.clone(), "first": first, "second": second,
                     "change_steps": change_steps, "heading_q": heading_q}

    def run_batch(batch, record_dir=None):
        n = len(batch)
        obs, setup = start_batch(batch)
        if args.scenario_set == "redirect":
            horizon = int(setup["change_steps"].max().item()) + deadline_steps + hold_steps + margin_steps
        else:
            horizon = deadline_steps + hold_steps + margin_steps
        push_steps = None
        push_vel = None
        if args.scenario_set == "push":
            push_time = torch.tensor([t["push_time_s"] for t in batch], device=device)
            push_steps = torch.round(push_time / dt).long()
            heading_deg = torch.tensor([t["push_heading_deg"] for t in batch], device=device)
            speed = torch.tensor([t["push_speed_mps"] for t in batch], device=device)
            angle = setup["heading_rad"] + torch.deg2rad(heading_deg)
            push_vel = torch.stack([speed * torch.cos(angle), speed * torch.sin(angle), torch.zeros_like(speed)], dim=-1)
        pos = torch.zeros(horizon, n, 3, device=device)
        vel = torch.zeros(horizon, n, 3, device=device)
        up_z = torch.zeros(horizon, n, device=device)
        dist = torch.zeros(horizon, n, device=device)
        tar = torch.zeros(horizon, n, 2, device=device)
        foot_force = torch.zeros(horizon, n, device=device)
        actions_abs_max = torch.zeros(horizon, n, device=device)
        writer = None
        frames = 0
        min_image_std = float("inf")
        if record_dir is not None:
            record_dir.mkdir(exist_ok=True)
            writer = imageio.get_writer(str(record_dir / "performance.mp4"), fps=30, codec="libx264",
                                        quality=7, macro_block_size=1)
        started = time.monotonic()
        with torch.no_grad():
            for step in range(horizon):
                if push_steps is not None:
                    due = (push_steps == step).nonzero(as_tuple=False).flatten()
                    if len(due) > 0:
                        sim._apply_root_velocity_impulse(push_vel[due], torch.zeros_like(push_vel[due]), due)
                action = policy(obs, step)
                obs, _, _, _, _ = env.step(action)
                state = sim.get_robot_state()
                force = sim.get_bodies_contact_buf().rigid_body_contact_forces
                root_pos = state.rigid_body_pos[:, anchor]
                for name, value in [("action", action), ("pos", state.rigid_body_pos), ("rot", state.rigid_body_rot),
                                    ("vel", state.rigid_body_vel), ("force", force)]:
                    assert torch.isfinite(value).all(), (step, name)
                pos[step] = root_pos
                vel[step] = state.rigid_body_vel[:, anchor]
                up_z[step] = kernels.body_up_z(state.rigid_body_rot[:, anchor])
                tar[step] = env.control_manager.components["target"]._tar_pos[:, :2]
                dist[step] = torch.linalg.norm(tar[step] - root_pos[:, :2], dim=-1)
                foot_force[step] = torch.linalg.norm(force[:, foot_ids], dim=-1).max(dim=-1).values
                actions_abs_max[step] = action.abs().max(dim=-1).values
                if writer is not None:
                    root = root_pos[:1].clone()
                    eye = root + torch.tensor([[3.0, -4.0, 2.0]], device=device)
                    look = root + torch.tensor([[0.0, 0.0, 0.15]], device=device)
                    camera.set_world_poses_from_view(eye, look)
                    sim._sim.render()
                    camera.update(dt)
                    rgb = camera.data.output["rgb"].torch[0].detach().cpu().numpy()[..., :3].astype(np.uint8)
                    assert rgb.shape == (480, 640, 3)
                    image_std = float(rgb.std())
                    min_image_std = min(min_image_std, image_std)
                    assert image_std > 5, (step, "blank render")
                    writer.append_data(rgb)
                    if step in (0, horizon // 2, horizon - 1):
                        Image.fromarray(rgb).save(record_dir / f"frame-{step:05d}.png")
                    frames += 1
        if writer is not None:
            writer.close()
        elapsed = time.monotonic() - started
        return {"horizon": horizon, "elapsed_wall_seconds": elapsed, "frames": frames,
                "min_image_std": min_image_std if frames else None,
                "pos": pos.cpu().numpy(), "vel": vel.cpu().numpy(), "up_z": up_z.cpu().numpy(),
                "dist": dist.cpu().numpy(), "tar": tar.cpu().numpy(), "foot_force": foot_force.cpu().numpy(),
                "action_abs_max": actions_abs_max.cpu().numpy(),
                "setup": {k: (v.cpu().numpy() if isinstance(v, torch.Tensor) else v) for k, v in setup.items()},
                "push_steps": push_steps.cpu().numpy() if push_steps is not None else None}

    def score_trial(data, k, trial):
        pos, vel, up_z, dist = data["pos"][:, k], data["vel"][:, k], data["up_z"][:, k], data["dist"][:, k]
        horizon = pos.shape[0]
        speed = np.linalg.norm(vel[:, :2], axis=-1)
        height = pos[:, 2]
        fallen = (height < FALL_HEIGHT) | (up_z < FALL_UP_Z)
        fall_step = int(np.argmax(fallen)) if fallen.any() else None
        t_ref = int(data["setup"]["change_steps"][k]) if args.scenario_set == "redirect" else 0
        reasons = []
        arrival = None
        for step in range(t_ref, horizon):
            if dist[step] < ARRIVAL_RADIUS:
                arrival = step
                break
        if arrival is None or arrival - t_ref > deadline_steps:
            reasons.append("no_arrival_within_15s")
        if fall_step is not None:
            reasons.append("fell")
        settle_strict = settle_loose = None
        if arrival is not None:
            for start in range(arrival, horizon - hold_steps + 1):
                window = slice(start, start + hold_steps)
                if settle_strict is None and (speed[window] < HOLD_SPEED).all() and (dist[window] < ARRIVAL_RADIUS).all():
                    settle_strict = start
                if settle_loose is None and (speed[window] < HOLD_SPEED).all() and (dist[window] < LOOSE_RADIUS).all():
                    settle_loose = start
                if settle_strict is not None and settle_loose is not None:
                    break
        if arrival is not None and settle_strict is None:
            reasons.append("no_two_second_hold_within_0.3m")
        success_strict = not reasons
        success_loose = (fall_step is None and arrival is not None and arrival - t_ref <= deadline_steps
                         and settle_loose is not None)
        first_target = data["setup"]["first"][k]
        summary = {
            "trial_id": trial["id"], "scenario": trial, "set": args.scenario_set,
            "horizon_steps": horizon, "reference_step": t_ref,
            "arrival_step": arrival, "time_to_arrival_s": None if arrival is None else round((arrival - t_ref) * dt, 3),
            "settle_step_strict": settle_strict,
            "time_to_settle_s": None if settle_strict is None else round((settle_strict - t_ref) * dt, 3),
            "success": success_strict, "success_loose": bool(success_loose), "failure_reasons": reasons,
            "fall_step": fall_step, "min_pelvis_height_m": float(height.min()), "min_up_z": float(up_z.min()),
            "max_planar_speed_mps": float(speed.max()), "final_distance_m": float(dist[-1]),
            "final_speed_mps": float(speed[-1]), "max_foot_contact_force_n": float(data["foot_force"][:, k].max()),
            "max_action_abs": float(data["action_abs_max"][:, k].max()),
            "start_xy": data["setup"]["start_xy"][k].tolist(), "heading_rad": float(data["setup"]["heading_rad"][k]),
            "first_target_xy": first_target.tolist(), "friction": trial.get("friction"),
        }
        if args.scenario_set == "redirect":
            summary["second_target_xy"] = data["setup"]["second"][k].tolist()
            arrived_first_before_change = bool((dist[:t_ref] < ARRIVAL_RADIUS).any()) if t_ref > 0 else False
            summary["reached_first_before_change"] = arrived_first_before_change
        if args.scenario_set == "push":
            summary["push_step"] = int(data["push_steps"][k])
        return summary

    def write_trace(path, data, k):
        with path.open("w") as stream:
            for step in range(data["pos"].shape[0]):
                stream.write(json.dumps({
                    "step": step + 1, "time_seconds": round((step + 1) * dt, 5),
                    "root_pos": [round(float(x), 5) for x in data["pos"][step, k]],
                    "root_vel": [round(float(x), 5) for x in data["vel"][step, k]],
                    "up_z": round(float(data["up_z"][step, k]), 5),
                    "target_xy": [round(float(x), 5) for x in data["tar"][step, k]],
                    "distance": round(float(data["dist"][step, k]), 5),
                    "foot_force": round(float(data["foot_force"][step, k]), 3)}) + "\n")

    def draw_topdown(path, data, summaries):
        size, scale = 900, 60.0  # pixels, pixels per metre; view centred on the start pose
        image = Image.new("RGB", (size, size), (248, 248, 248))
        draw = ImageDraw.Draw(image)
        centre = size / 2
        for metre in range(-7, 8):
            offset = centre + metre * scale
            colour = (200, 200, 200) if metre else (150, 150, 150)
            draw.line([(offset, 0), (offset, size)], fill=colour)
            draw.line([(0, offset), (size, offset)], fill=colour)
        for k, summary in enumerate(summaries):
            heading = data["setup"]["heading_rad"][k]
            start = data["setup"]["start_xy"][k]
            c, s = math.cos(-heading), math.sin(-heading)

            def to_px(xy):
                x, y = xy[0] - start[0], xy[1] - start[1]
                rx, ry = c * x - s * y, s * x + c * y
                return centre + rx * scale, centre - ry * scale
            colour = (40, 140, 60) if summary["success"] else (200, 60, 60)
            points = [to_px(p) for p in data["pos"][:, k, :2]]
            draw.line(points, fill=colour, width=2)
            for key in ("first_target_xy", "second_target_xy"):
                if key in summary:
                    tx, ty = to_px(summary[key])
                    r = ARRIVAL_RADIUS * scale
                    draw.ellipse([tx - r, ty - r, tx + r, ty + r], outline=(30, 30, 200), width=2)
            if summary["fall_step"] is not None:
                fx, fy = to_px(data["pos"][summary["fall_step"], k, :2])
                draw.rectangle([fx - 5, fy - 5, fx + 5, fy + 5], fill=(200, 60, 60))
        draw.text((10, 10), f"{args.controller} / {args.scenario_set}: top-down, start at centre, initial heading +x; "
                            f"green=success red=failure; circles=0.3 m arrival radius; grid 1 m", fill=(0, 0, 0))
        image.save(path)

    summaries = []
    trace_lines = 0
    if args.record:
        for trial in trials:
            directory = args.output / f"trial-{trial['id']:03d}"
            data = run_batch([trial], record_dir=directory)
            summary = score_trial(data, 0, trial)
            summary.update({"recorded_frames": data["frames"], "expected_control_steps": data["horizon"],
                            "complete": data["frames"] == data["horizon"], "elapsed_wall_seconds": data["elapsed_wall_seconds"],
                            "minimum_image_std": data["min_image_std"]})
            write_trace(directory / "trace.jsonl", data, 0)
            draw_topdown(directory / "topdown.png", data, [summary])
            (directory / "summary.json").write_text(json.dumps(summary, indent=2, default=encode) + "\n")
            summaries.append(summary)
            print("STUDIO_TRIAL " + json.dumps({k: summary[k] for k in ("trial_id", "success", "failure_reasons", "time_to_arrival_s", "time_to_settle_s")}), flush=True)
    else:
        data = run_batch(trials)
        with (args.output / f"trace-{args.scenario_set}.jsonl").open("w") as stream:
            for k, trial in enumerate(trials):
                summary = score_trial(data, k, trial)
                summaries.append(summary)
                for step in range(data["horizon"]):
                    stream.write(json.dumps({
                        "trial_id": trial["id"], "step": step + 1,
                        "root_pos": [round(float(x), 4) for x in data["pos"][step, k]],
                        "speed": round(float(np.linalg.norm(data["vel"][step, k, :2])), 4),
                        "up_z": round(float(data["up_z"][step, k]), 4),
                        "distance": round(float(data["dist"][step, k]), 4),
                        "target_xy": [round(float(x), 4) for x in data["tar"][step, k]],
                        "foot_force": round(float(data["foot_force"][step, k]), 2)}) + "\n")
                    trace_lines += 1
        draw_topdown(args.output / f"topdown-{args.scenario_set}.png", data, summaries)
        print(f"Batch of {len(trials)} trials took {data['elapsed_wall_seconds']:.1f}s for {data['horizon']} steps", flush=True)
    save("trials.json", summaries)
    count = len(summaries)
    successes = sum(s["success"] for s in summaries)
    measurements = {
        "controller": args.controller, "set": args.scenario_set, "trials": count,
        "successes": successes, "success_rate": successes / count,
        "successes_loose": sum(s["success_loose"] for s in summaries),
        "arrived_within_15s": sum(s["arrival_step"] is not None and (s["arrival_step"] - s["reference_step"]) <= deadline_steps for s in summaries),
        "falls": sum(s["fall_step"] is not None for s in summaries),
        "failure_reasons": {r: sum(r in s["failure_reasons"] for s in summaries)
                            for r in ("no_arrival_within_15s", "fell", "no_two_second_hold_within_0.3m")},
        "mean_time_to_arrival_s": float(np.mean([s["time_to_arrival_s"] for s in summaries if s["time_to_arrival_s"] is not None])) if any(s["time_to_arrival_s"] is not None for s in summaries) else None,
        "mean_time_to_settle_s": float(np.mean([s["time_to_settle_s"] for s in summaries if s["time_to_settle_s"] is not None])) if any(s["time_to_settle_s"] is not None for s in summaries) else None,
        "min_pelvis_height_m": min(s["min_pelvis_height_m"] for s in summaries),
        "max_planar_speed_mps": max(s["max_planar_speed_mps"] for s in summaries),
        "required_successes_per_100": 90,
        "gate_passed_90_percent": successes / count >= 0.9,
        "trace_lines": trace_lines,
    }
    save("measurements.json", measurements)
    print("STUDIO_MEASUREMENTS " + json.dumps(measurements), flush=True)
    sim._sim.stage.Export(str(args.output / "final-scene.usda"))
    sim._sim.stop()
    return {"status": "checks_passed_shutdown_pending", "controller": args.controller, "set": args.scenario_set,
            "trials": count, "recorded_frames": sum(s.get("recorded_frames", 0) for s in summaries),
            "all_trials_complete": all(s.get("complete", True) for s in summaries),
            "all_sampled_states_actions_finite": True, "physics_hz": 120, "control_hz": 30,
            "measurements": measurements, "training_performed": False}


exit_code = 1
try:
    result = run_evaluation()
    from isaaclab.sim import SimulationContext
    SimulationContext.clear_instance()
    assert SimulationContext.instance() is None and app.context.get_stage() is None
    assert app.config["fast_shutdown"] is True
    result["shutdown"] = {"simulation_context_cleared": True, "stage_closed": True,
                          "fast_shutdown": True, "skip_cleanup": False}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    exit_code = 0
except BaseException:
    traceback.print_exc()
    raise
finally:
    app.close(wait_for_replicator=True, skip_cleanup=False, exit_code=exit_code)
raise RuntimeError("Kit standalone shutdown unexpectedly returned")
