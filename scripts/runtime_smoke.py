"""Run inside the pinned image: GPU computation, PhysX fall/contact, and RTX image."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import time
import traceback

from protomotions.utils.simulator_imports import import_simulator_before_torch

AppLauncher = import_simulator_before_torch("isaaclab")
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
started = time.monotonic()
args.output.mkdir(parents=True, exist_ok=True)
app = AppLauncher(args, fast_shutdown=False).app

try:
    import numpy as np
    import torch
    from PIL import Image
    from isaaclab.assets import RigidObject, RigidObjectCfg
    from isaaclab.sensors.camera import Camera, CameraCfg
    import isaaclab.sim as sim_utils
    from isaaclab_physx.physics import PhysxCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg
    from protomotions.simulator.isaaclab.simulator import IsaacLabSimulator

    assert torch.cuda.is_available(), "CUDA unavailable"
    assert str(args.device) == "cuda:0", args.device
    values = torch.ones((128, 128), device="cuda:0")
    product = values @ values
    torch.cuda.synchronize()
    assert torch.equal(product, torch.full_like(product, 128.0)), "GPU matmul result mismatch"

    dt = 1.0 / 60.0
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(
        device="cuda:0", dt=dt, physics=PhysxCfg(),
        log_dir=str(args.output / "physics-logs"),
    ))
    assert "physx" in sim.physics_manager.__module__.lower(), sim.physics_manager
    assert sim.device == "cuda:0", sim.device
    # Native primitives avoid introducing downloaded character/scene assets in M0.
    floor = sim_utils.CuboidCfg(
        size=(10.0, 10.0, 0.1), collision_props=sim_utils.CollisionPropertiesCfg(),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.3, 0.3, 0.3)),
    )
    floor.func("/World/Floor", floor, translation=(0.0, 0.0, -0.05))
    light = sim_utils.DomeLightCfg(intensity=2000.0)
    light.func("/World/Light", light)
    cube = RigidObject(RigidObjectCfg(
        prim_path="/World/Cube",
        spawn=sim_utils.CuboidCfg(
            size=(0.5, 0.5, 0.5), rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props=sim_utils.MassPropertiesCfg(mass=1.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.1, 0.3, 0.9)),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(0.0, 0.0, 2.0)),
    ))
    camera = Camera(CameraCfg(
        prim_path="/World/Camera", update_period=0, width=640, height=480,
        data_types=["rgb"], renderer_cfg=IsaacRtxRendererCfg(),
        spawn=sim_utils.PinholeCameraCfg(focal_length=24.0, horizontal_aperture=20.955,
                                       clipping_range=(0.1, 100.0)),
    ))
    sim.reset()
    camera.set_world_poses_from_view(
        torch.tensor([[3.0, -4.0, 3.0]], device=sim.device),
        torch.tensor([[0.0, 0.0, 0.5]], device=sim.device),
    )
    initial_z = float(cube.data.root_pos_w.torch[0, 2])
    positions, velocities = [], []
    for step in range(240):
        cube.write_data_to_sim()
        sim.step()
        cube.update(dt)
        camera.update(dt)
        position = cube.data.root_pos_w.torch[0]
        velocity = cube.data.root_lin_vel_w.torch[0]
        assert torch.isfinite(position).all() and torch.isfinite(velocity).all(), step
        positions.append(position.cpu().tolist())
        velocities.append(velocity.cpu().tolist())
    assert positions[9][2] < initial_z - 0.05, "Cube did not fall under gravity"
    assert abs(positions[-1][2] - 0.25) < 0.03, "Cube did not rest on the floor"
    assert min(p[2] for p in positions) > 0.20, "Cube penetrated the floor"
    assert max(np.linalg.norm(v) for v in velocities[-30:]) < 0.1, "Cube did not settle"
    assert np.ptp(np.asarray(positions[-30:])[:, 2]) < 0.01, "Contact height is unstable"
    rgb = camera.data.output["rgb"].torch[0].detach().cpu().numpy()
    rgb = np.asarray(rgb)[..., :3]
    assert rgb.shape == (480, 640, 3), rgb.shape
    assert np.isfinite(rgb).all() and float(rgb.std()) > 5.0, "Blank/invalid RTX image"
    Image.fromarray(rgb.astype(np.uint8)).save(args.output / "render.png")
    sim.stage.Export(str(args.output / "scene.usda"))
    (args.output / "trajectory.json").write_text(json.dumps({
        "dt": dt, "positions": positions, "linear_velocities": velocities
    }, indent=2) + "\n")
    result = {
        "status": "checks_passed_shutdown_pending", "python": platform.python_version(),
        "versions": {name: metadata.version(name) for name in
                     ["isaacsim", "isaaclab", "protomotions", "torch", "moviepy", "pillow"]},
        "gpu": torch.cuda.get_device_name(0), "cuda_compute": "128x128 matrix multiplication passed",
        "physics_manager": sim.physics_manager.__module__, "physics_device": sim.device,
        "protomotions_backend_import": IsaacLabSimulator.__module__,
        "initial_height": initial_z, "final_height": positions[-1][2], "steps": 240,
        "render_shape": list(rgb.shape), "render_std": float(rgb.std()),
        "sources": json.loads(Path("/opt/studio/source-revisions.json").read_text()),
    }
    sim.stop()
except BaseException:
    traceback.print_exc()
    raise
finally:
    app.close()

result["status"] = "passed"
result["elapsed_seconds"] = time.monotonic() - started
(args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print("STUDIO_RUNTIME_SMOKE_PASSED", flush=True)
