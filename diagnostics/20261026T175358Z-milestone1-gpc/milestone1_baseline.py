"""Instrument pinned ProtoMotions inference with complete trials, metrics and RTX video."""
import argparse
import dataclasses
import json
from pathlib import Path
import time
import traceback

from protomotions.utils.simulator_imports import import_simulator_before_torch
AppLauncher = import_simulator_before_torch('isaaclab')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--family', choices=['tracker', 'gpc'], required=True)
parser.add_argument('--seed', type=int, default=0)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
app = AppLauncher(args).app


def run_baseline():
    import numpy as np
    import torch
    import imageio.v2 as imageio
    from PIL import Image
    from lightning.fabric import Fabric
    from isaaclab.sensors.camera import Camera, CameraCfg
    from isaaclab_physx.renderers import IsaacRtxRendererCfg
    import isaaclab.sim as sim_utils
    from protomotions.simulator.factory import update_simulator_config_for_test
    from protomotions.simulator.base_simulator.utils import convert_friction_for_simulator
    from protomotions.utils.component_builder import build_all_components
    from protomotions.utils.hydra_replacement import get_class
    from protomotions.envs.mdp_component import MdpComponent

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

    def save(name, value):
        (args.output / name).write_text(json.dumps(value, default=encode, indent=2, allow_nan=False) + '\n')

    torch.set_num_threads(4)
    Fabric.seed_everything(args.seed)
    fabric = Fabric(accelerator='gpu', devices=1, num_nodes=1, loggers=[], callbacks=[])
    fabric.launch()
    device = fabric.device
    assets = Path('/studio/assets')
    if args.family == 'tracker':
        model_dir = assets / 'data/pretrained_models/motion_tracker/soma-bones'
        checkpoint = model_dir / 'last_lab.ckpt'
        motion = assets / 'data/motion_for_trackers/soma23_bones_seed_mini.pt'
    else:
        model_dir = assets / 'data/pretrained_models/gpc_prior/soma_bones'
        checkpoint = model_dir / 'inference_last.ckpt'
        motion = assets / 'data/motion_for_trackers/crouch_soma23.pt'
    configs = torch.load(model_dir / 'resolved_configs_inference.pt', map_location='cpu', weights_only=False)
    robot, sim_cfg = configs['robot'], configs['simulator']
    source_simulator = sim_cfg._target_
    source_control_hz = sim_cfg.sim.fps / sim_cfg.sim.decimation
    if '.isaaclab.' not in sim_cfg._target_:
        sim_cfg = update_simulator_config_for_test(sim_cfg, 'isaaclab', robot)
    sim_cfg.w_last, sim_cfg.headless, sim_cfg.num_envs = True, True, 1
    assert sim_cfg.sim.fps == 120 and sim_cfg.sim.decimation == 4
    assert source_control_hz == 30
    configs['simulator'] = sim_cfg
    configs['motion_lib'].motion_file = str(motion)
    configs['motion_lib'].motion_file_shard_indices = None
    assert configs['scene_lib'].scene_file is None
    terrain_cfg, sim_cfg = convert_friction_for_simulator(configs['terrain'], sim_cfg)
    configs['terrain'], configs['simulator'] = terrain_cfg, sim_cfg
    save('resolved-configs.json', configs)
    save('run-contract.json', {'family': args.family, 'seed': args.seed,
        'checkpoint': str(checkpoint), 'motion_file': str(motion),
        'source_simulator_target': source_simulator, 'selected_simulator_target': sim_cfg._target_,
        'physics_hz': 120, 'decimation': 4, 'control_hz': 30, 'num_envs': 1,
        'recording': {'width': 640, 'height': 480, 'fps': 30, 'all_trials': True},
        'semantic_body_names': robot.kinematic_info.body_names,
        'semantic_dof_names': robot.kinematic_info.dof_names,
        'upstream_evaluation': 'MimicEvaluator.evaluate, with full clip lengths' if args.family == 'tracker' else '20-second prior rollout; no task success claim',
        'training_performed': False, 'dataset_eligibility_record': '/studio/license.json'})
    components = build_all_components(terrain_cfg, configs['scene_lib'], configs['motion_lib'],
        sim_cfg, robot, device, simulation_app=app)
    sim = components['simulator']
    camera = Camera(CameraCfg(
        prim_path='/World/StudioCamera', update_period=0, width=640, height=480,
        data_types=['rgb'], renderer_cfg=IsaacRtxRendererCfg(),
        spawn=sim_utils.PinholeCameraCfg(focal_length=24.0, horizontal_aperture=20.955,
                                       clipping_range=(0.1, 1000.0))))
    env = get_class(configs['env']._target_)(config=configs['env'], robot_config=robot,
        device=device, terrain=components['terrain'], scene_lib=components['scene_lib'],
        motion_lib=components['motion_lib'], simulator=sim)
    ordering = sim._get_sim_body_ordering()
    mapping = sim.data_conversion
    assert len(ordering.body_names) == 23 and len(ordering.dof_names) == 66
    for names, expected, common, inverse in [
        (ordering.body_names, robot.kinematic_info.body_names, mapping.body_convert_to_common, mapping.body_convert_to_sim),
        (ordering.dof_names, robot.kinematic_info.dof_names, mapping.dof_convert_to_common, mapping.dof_convert_to_sim),
    ]:
        assert [names[i] for i in common.tolist()] == expected
        assert torch.equal(common[inverse], torch.arange(len(names), device=device))
    assert abs(env.dt - 1 / 30) < 1e-9
    save('actual-simulator.json', {'ordering': ordering, 'mapping': mapping,
        'physics': sim._sim.cfg.to_dict(), 'scene': sim._scene.cfg.to_dict(),
        'p_gains_common': sim._common_p_gains, 'd_gains_common': sim._common_d_gains,
        'torque_limits_common': sim._torque_limits_common, 'contact_sensors': list(sim._contact_sensor_map)})
    agent = get_class(configs['agent']._target_)(config=configs['agent'], env=env, fabric=fabric,
                                               root_dir=args.output / 'upstream')
    agent.setup()
    agent.load(checkpoint, load_env=False, load_training_state=False)
    agent.eval()
    sim._sim.stage.Export(str(args.output / 'initial-scene.usda'))
    lengths = env.motion_lib.get_motion_length(None)
    full_steps = (lengths / env.dt).floor().long()
    save('motion-inventory.json', {'num_motions': env.motion_lib.num_motions(),
        'length_seconds': lengths, 'control_steps': full_steps,
        'reference_frames': env.motion_lib.get_motion_num_frames(None)})
    evaluator = agent.evaluator
    trials = []

    class Recorder:
        def __init__(self, trial_id, expected_steps):
            self.trial_id, self.expected_steps = trial_id, expected_steps
            self.frames = 0
            self.first_termination = None
            self.first_tracking_failure = None
            self.max_contact_force = 0.0
            self.maximum_quaternion_norm_error = 0.0
            self.started = time.monotonic()
            self.directory = args.output / f'trial-{trial_id:03d}'
            self.directory.mkdir()
            self.trace = (self.directory / 'trace.jsonl').open('w', buffering=1)
            self.writer = imageio.get_writer(str(self.directory / 'performance.mp4'), fps=30,
                codec='libx264', quality=7, macro_block_size=1)
            self.minimum_image_std = float('inf')

        def record(self, action):
            state = sim.get_robot_state()
            force = sim.get_bodies_contact_buf().rigid_body_contact_forces
            failed = bool(evaluator._motion_failed[self.trial_id]) if args.family == 'tracker' else None
            self.trace.write(json.dumps({'step': self.frames + 1, 'time_seconds': (self.frames + 1) * env.dt,
                'motion_time_seconds': env.motion_manager.motion_times,
                'action_raw': action, 'action_processed': env._current_processed_action,
                'state': state, 'contact_forces': force, 'termination': env.terminate_buf,
                'done': env.reset_buf, 'upstream_tracking_failed': failed}, default=encode) + '\n')
            for name, value in [('action', action), ('processed_action', env._current_processed_action),
                                ('forces', force)] + [(f.name, getattr(state, f.name)) for f in dataclasses.fields(state)]:
                if isinstance(value, torch.Tensor):
                    assert torch.isfinite(value).all(), (self.trial_id, self.frames, name)
            norm_error = float((torch.linalg.vector_norm(state.rigid_body_rot, dim=-1) - 1).abs().max())
            self.maximum_quaternion_norm_error = max(self.maximum_quaternion_norm_error, norm_error)
            assert norm_error < 0.001, (self.trial_id, self.frames, norm_error)
            self.max_contact_force = max(self.max_contact_force, float(torch.linalg.vector_norm(force, dim=-1).max()))
            if bool(env.terminate_buf[0]) and self.first_termination is None:
                self.first_termination = self.frames + 1
            if failed and self.first_tracking_failure is None:
                self.first_tracking_failure = self.frames + 1
            root = state.rigid_body_pos[:, 0].clone()
            eye = root + torch.tensor([[3.0, -4.0, 2.0]], device=device)
            target = root + torch.tensor([[0.0, 0.0, 0.15]], device=device)
            camera.set_world_poses_from_view(eye, target)
            sim._sim.render()
            camera.update(env.dt)
            rgb = camera.data.output['rgb'].torch[0].detach().cpu().numpy()[..., :3].astype(np.uint8)
            assert rgb.shape == (480, 640, 3)
            image_std = float(rgb.std())
            self.minimum_image_std = min(self.minimum_image_std, image_std)
            assert image_std > 5, (self.trial_id, self.frames, 'blank render')
            self.writer.append_data(rgb)
            if self.frames in (0, self.expected_steps // 2, self.expected_steps - 1):
                Image.fromarray(rgb).save(self.directory / f'frame-{self.frames:05d}.png')
            self.frames += 1

        def close(self, completed):
            self.trace.close()
            self.writer.close()
            summary = {'trial_id': self.trial_id, 'expected_control_steps': self.expected_steps,
                'recorded_frames': self.frames, 'complete': completed and self.frames == self.expected_steps,
                'first_termination_step': self.first_termination,
                'first_upstream_tracking_failure_step': self.first_tracking_failure,
                'maximum_contact_force_newtons': self.max_contact_force,
                'maximum_quaternion_norm_error': self.maximum_quaternion_norm_error,
                'minimum_image_std': self.minimum_image_std if self.frames else None,
                'elapsed_wall_seconds': time.monotonic() - self.started,
                'resets_inside_trial': 0,
                'failure_policy': 'A termination/failure marks the attempt failed; subsequent frames remain recorded without resetting.'}
            if args.family == 'tracker':
                summary['upstream_tracking_failed'] = bool(evaluator._motion_failed[self.trial_id])
                summary['studio_attempt_failed'] = summary['upstream_tracking_failed'] or self.first_termination is not None
                summary['metrics'] = {name: {'mean': float(evaluator._component_value_sum[name][self.trial_id] /
                    evaluator._component_step_count[name][self.trial_id].clamp_min(1)),
                    'maximum': float(evaluator._component_value_max[name][self.trial_id]),
                    'steps': int(evaluator._component_step_count[name][self.trial_id])}
                    for name in evaluator._component_step_count if int(evaluator._component_step_count[name][self.trial_id]) > 0}
            save(f'trial-{self.trial_id:03d}/summary.json', summary)
            trials.append(summary)
            save('trials.json', trials)
            print('STUDIO_TRIAL ' + json.dumps(summary), flush=True)
            return summary

    if args.family == 'tracker':
        # Preserve the upstream evaluator and thresholds; lift only its 600-step cap
        # to include the complete longest bundled clip, using runtime lengths.
        original_max_steps = evaluator.config.max_eval_steps
        evaluator.config.max_eval_steps = max(original_max_steps, int(full_steps.max()))
        save('evaluation-contract.json', {'original_max_steps': original_max_steps,
            'selected_max_steps': evaluator.config.max_eval_steps,
            'components': evaluator.config.evaluation_components,
            'reset_noise_and_push': 'disabled by upstream evaluate()', 'all_motions': True})
        original_episode = evaluator.evaluate_episode
        original_step = evaluator._on_episode_step
        active = [None]

        def record_step(env_ids, extras, actions):
            original_step(env_ids, extras, actions)
            active[0].record(actions)

        def record_episode(env_ids, max_steps):
            trial_id = int(evaluator._episode_ctx.motion_ids[0])
            assert env_ids.numel() == 1
            recorder = Recorder(trial_id, max_steps)
            active[0] = recorder
            completed = False
            try:
                original_episode(env_ids, max_steps)
                completed = True
            finally:
                recorder.close(completed)
                active[0] = None
        evaluator.evaluate_episode = record_episode
        evaluator._on_episode_step = record_step
        evaluation_log, score, items = evaluator.evaluate()
        assert items == env.motion_lib.num_motions() == len(trials)
        assert sum(t['recorded_frames'] for t in trials) == int(full_steps.sum())
        summary = {'evaluation_log': evaluation_log, 'upstream_score': score, 'items': items,
                   'studio_failed_attempts': sum(t['studio_attempt_failed'] for t in trials)}
    else:
        # The prior's empty full-eval configuration does not test any behavior.
        # Execute an explicit 20-second rollout with only current-state model inputs.
        assert agent.model.get_inference_in_keys() == ['max_coords_obs']
        evaluator._disable_perturbations()
        env_ids = torch.arange(1, device=device)
        env.motion_manager.motion_ids[:] = 0
        env.motion_manager.motion_times[:] = 0
        recorder = Recorder(0, 600)
        completed = False
        try:
            with torch.no_grad():
                obs, _ = env.reset(env_ids, sample_flat=True, disable_motion_resample=True)
                agent.model.reset_rollout_context(env_ids=env_ids)
                for step in range(600):
                    agent.pre_collect_step(step)
                    td = agent.obs_dict_to_tensordict(agent.add_agent_info_to_obs(obs))
                    action = evaluator._policy_action(td)
                    obs, _, _, _, _ = env.step(action)
                    recorder.record(action)
            completed = True
        finally:
            recorder.close(completed)
            evaluator._restore_perturbations()
        summary = {'items': 1, 'rollout_seconds': 20, 'model_inputs': ['max_coords_obs'],
                   'embedded_decoder_loaded': True, 'task_adaptation': False, 'task_success_claimed': False}
    assert all(t['complete'] for t in trials)
    assert max(t['maximum_contact_force_newtons'] for t in trials) > 1.0
    save('measurements.json', summary)
    sim._sim.stage.Export(str(args.output / 'final-scene.usda'))
    sim._sim.stop()
    return {'status': 'checks_passed_shutdown_pending', 'family': args.family, 'seed': args.seed,
        'physics_hz': 120, 'control_hz': 30, 'trials': len(trials),
        'recorded_frames': sum(t['recorded_frames'] for t in trials),
        'all_trials_complete': True, 'all_sampled_states_actions_finite': True,
        'measurements': summary, 'training_performed': False}

exit_code = 1
try:
    result = run_baseline()
    from isaaclab.sim import SimulationContext
    SimulationContext.clear_instance()
    assert SimulationContext.instance() is None and app.context.get_stage() is None
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
