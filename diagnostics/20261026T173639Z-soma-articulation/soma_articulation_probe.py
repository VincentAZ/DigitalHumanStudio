"""Load the pinned SOMA articulation without any motion library or learned actions.

This checks the physical asset adapter, not the M1 motion-tracking acceptance gate.
"""
import argparse
import dataclasses
import json
from pathlib import Path
import traceback

from protomotions.utils.simulator_imports import import_simulator_before_torch
AppLauncher = import_simulator_before_torch('isaaclab')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
app = AppLauncher(args).app


def run_probe():
    import torch
    from protomotions.simulator.factory import update_simulator_config_for_test
    from protomotions.simulator.base_simulator.utils import convert_friction_for_simulator
    from protomotions.utils.component_builder import (
        build_terrain_from_config, build_scene_lib_from_config, build_simulator_from_config,
    )

    def encode(obj):
        if isinstance(obj, torch.Tensor):
            return obj.detach().cpu().tolist()
        if dataclasses.is_dataclass(obj):
            return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
        return str(obj)

    def save(name, value):
        (args.output / name).write_text(json.dumps(value, default=encode, indent=2) + '\n')

    torch.manual_seed(0)
    device = torch.device('cuda:0')
    configs = torch.load('/studio/config.pt', map_location='cpu', weights_only=False)
    robot, cfg = configs['robot'], configs['simulator']
    original_rate = cfg.sim.fps / cfg.sim.decimation
    if '.isaaclab.' not in cfg._target_:
        cfg = update_simulator_config_for_test(cfg, 'isaaclab', robot)
    cfg.w_last, cfg.headless, cfg.num_envs = True, True, 1
    assert cfg.sim.fps == 120 and cfg.sim.decimation == 4 and original_rate == 30
    terrain_cfg, cfg = convert_friction_for_simulator(configs['terrain'], cfg)
    assert configs['scene_lib'].scene_file is None
    save('requested-config.json', {'robot': robot, 'simulator': cfg,
        'terrain': terrain_cfg, 'scene_lib': configs['scene_lib'],
        'overrides': {'num_envs': 1, 'headless': True, 'w_last': True},
        'motion_data_mounted': False, 'policy_used': False})
    terrain = build_terrain_from_config(terrain_cfg, 1, device)
    scene_lib = build_scene_lib_from_config(configs['scene_lib'], 1, device, terrain)
    sim = build_simulator_from_config(cfg, robot, terrain, scene_lib, device, simulation_app=app)
    sim._initialize_with_markers(None)
    ordering = sim._get_sim_body_ordering()
    mapping = sim.data_conversion
    save('actual-mapping.json', {'ordering': ordering, 'conversion': mapping,
        'joint_backend_names': sim._robot.joint_names,
        'p_gains_common': sim._common_p_gains, 'd_gains_common': sim._common_d_gains,
        'torque_limits_common': sim._torque_limits_common,
        'contact_sensors': list(sim._contact_sensor_map),
        'scene_config': sim._scene.cfg.to_dict(), 'simulation_config': sim._sim.cfg.to_dict()})
    assert len(ordering.body_names) == 23 and len(ordering.dof_names) == 66
    for names, expected, to_common, to_sim in [
        (ordering.body_names, robot.kinematic_info.body_names,
         mapping.body_convert_to_common, mapping.body_convert_to_sim),
        (ordering.dof_names, robot.kinematic_info.dof_names,
         mapping.dof_convert_to_common, mapping.dof_convert_to_sim),
    ]:
        assert [names[i] for i in to_common.tolist()] == expected
        assert torch.equal(to_common[to_sim], torch.arange(len(names), device=device))
    assert set(sim._contact_sensor_map) == set(robot.contact_bodies)
    assert abs(sim.dt - 1 / 30) < 1e-10
    assert 'physx' in sim._sim.physics_manager.__module__.lower()
    sim._sim.stage.Export(str(args.output / 'loaded-scene.usda'))
    reset = sim.get_default_robot_reset_state()
    # Keep the complete body inside the finite flat mesh and above its surface.
    reset.root_pos[:] = torch.tensor([5.0, 5.0, 1.15], device=device)
    maximum_contact_force = 0.0
    save('synthetic-reset.json', reset)
    sim.reset_envs(reset)
    # An explicit zero-action asset probe, not a motion-tracking or balance test.
    with (args.output / 'synthetic-trace.jsonl').open('w', buffering=1) as trace:
        for step in range(30):
            sim.step(torch.zeros((1, 66), device=device))
            state = sim.get_robot_state()
            forces = sim.get_bodies_contact_buf().rigid_body_contact_forces
            trace.write(json.dumps({'step': step + 1, 'time_seconds': (step + 1) * sim.dt,
                                    'state': state, 'contact_forces': forces}, default=encode) + '\n')
            for field in dataclasses.fields(state):
                value = getattr(state, field.name)
                if isinstance(value, torch.Tensor):
                    assert torch.isfinite(value).all(), (step, field.name)
            assert torch.isfinite(forces).all(), step
            maximum_contact_force = max(maximum_contact_force, float(torch.linalg.vector_norm(forces, dim=-1).max()))
    save('contact-summary.json', {'maximum_contact_force_newtons': maximum_contact_force,
                                 'reset_position': [5.0, 5.0, 1.15]})
    assert maximum_contact_force > 1.0, 'No measurable foot/toe ground contact'
    sim._sim.stop()
    return {'status': 'checks_passed_shutdown_pending', 'scope': 'articulation_adapter_only',
        'physics_hz': 120, 'control_hz': 30, 'control_steps': 30,
        'bodies': 23, 'joints': 66, 'finite_samples': 30,
        'maximum_contact_force_newtons': maximum_contact_force,
        'motion_data_loaded': False, 'policy_used': False,
        'tracking_quality_tested': False, 'balance_tested': False,
        'sources': json.loads(Path('/opt/studio/source-revisions.json').read_text())}

exit_code = 1
try:
    result = run_probe()
    from isaaclab.sim import SimulationContext
    SimulationContext.clear_instance()
    assert SimulationContext.instance() is None
    assert app.context.get_stage() is None
    assert app.config['fast_shutdown'] is True
    result['shutdown'] = {'simulation_context_cleared': True, 'stage_closed': True,
                          'fast_shutdown': True, 'skip_cleanup': False}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    exit_code = 0
except BaseException:
    traceback.print_exc()
    raise
finally:
    app.close(wait_for_replicator=True, skip_cleanup=False, exit_code=exit_code)
raise RuntimeError('Kit standalone shutdown unexpectedly returned')
