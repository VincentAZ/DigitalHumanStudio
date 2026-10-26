"""CPU-only checkpoint/config contract checks inside the locked runtime image."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import torch
from protomotions.utils.hydra_replacement import get_class
from protomotions.agents.utils.normalization import materialize_lazy_running_stats_from_state_dict
from protomotions.simulator.factory import update_simulator_config_for_test

parser = argparse.ArgumentParser()
parser.add_argument('--assets', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(4)

def encode(obj):
    if isinstance(obj, torch.Tensor):
        return obj.detach().cpu().tolist()
    if dataclasses.is_dataclass(obj):
        return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    return str(obj)

reports = {}
for name, relative, checkpoint_name in [
    ('tracker', 'data/pretrained_models/motion_tracker/soma-bones', 'last_lab.ckpt'),
    ('gpc', 'data/pretrained_models/gpc_prior/soma_bones', 'inference_last.ckpt'),
]:
    directory = args.assets / relative
    configs = torch.load(directory / 'resolved_configs_inference.pt', map_location='cpu', weights_only=False)
    robot, simulator = configs['robot'], configs['simulator']
    source_target = simulator._target_
    original_control_hz = simulator.sim.fps / simulator.sim.decimation
    if '.isaaclab.' not in simulator._target_:
        simulator = update_simulator_config_for_test(simulator, 'isaaclab', robot)
    assert simulator.sim.fps == 120 and simulator.sim.decimation == 4
    assert simulator.sim.fps / simulator.sim.decimation == original_control_hz
    assert robot.number_of_actions == 66
    body_names, dof_names = robot.kinematic_info.body_names, robot.kinematic_info.dof_names
    assert len(body_names) == len(set(body_names)) == 23
    assert len(dof_names) == len(set(dof_names)) == 66
    xml = ET.parse(args.assets / 'protomotions/data/assets/mjcf/soma23_humanoid.xml')
    assert [body.attrib['name'] for body in xml.findall('.//worldbody//body')] == body_names
    assert [joint.attrib['name'] for joint in xml.findall('.//worldbody//joint')] == dof_names
    checkpoint = torch.load(directory / checkpoint_name, map_location='cpu', weights_only=False)
    model = get_class(configs['agent'].model._target_)(config=configs['agent'].model)
    state = checkpoint['model']
    materialize_lazy_running_stats_from_state_dict(model, state)
    model.materialize_from_state_dict(state)
    incompatible = model.load_state_dict(state, strict=True)
    model.eval()
    assert not incompatible.missing_keys and not incompatible.unexpected_keys
    assert all(torch.isfinite(value).all() for value in state.values() if isinstance(value, torch.Tensor))
    report = {
        'status': 'passed_cpu_contract_checks', 'checkpoint': str(directory / checkpoint_name),
        'source_simulator_target': source_target, 'selected_simulator_target': simulator._target_,
        'physics_hz': simulator.sim.fps, 'decimation': simulator.sim.decimation,
        'control_hz': original_control_hz, 'body_names': body_names, 'dof_names': dof_names,
        'model_class': configs['agent'].model._target_, 'model_state_keys': len(state),
        'strict_model_load': True, 'weights_finite': True,
        'control': robot.control, 'physics': simulator.sim,
        'model_inference_inputs': list(model.in_keys),
        'note': 'CPU contract check only. No motion data loaded; no simulator or task adaptation executed.',
    }
    if name == 'gpc':
        assert configs['agent'].model.latent_decoder.module_config is not None
        assert model.get_inference_in_keys() == ['max_coords_obs']
        report['embedded_decoder'] = True
        report['latent_decoder'] = configs['agent'].model.latent_decoder
    (args.output / f'{name}-contract.json').write_text(json.dumps(report, default=encode, indent=2) + '\n')
    (args.output / f'{name}-resolved-configs.json').write_text(json.dumps(configs, default=encode, indent=2) + '\n')
    reports[name] = {key: report[key] for key in ('status', 'model_state_keys', 'physics_hz', 'control_hz', 'strict_model_load')}
    print(name, reports[name], flush=True)
    del model, state, checkpoint
(args.output / 'preflight.json').write_text(json.dumps(reports, indent=2) + '\n')
