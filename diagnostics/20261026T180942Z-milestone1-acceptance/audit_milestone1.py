"""Audit completed baseline traces and actual controller settings without starting Isaac."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def finite(value):
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    return not isinstance(value, float) or math.isfinite(value)


def audit(directory):
    result = read(directory / 'result.json')
    config = read(directory / 'resolved-configs.json')
    actual = read(directory / 'actual-simulator.json')
    contract = read(directory / 'run-contract.json')
    trials = read(directory / 'trials.json')
    assert result['all_trials_complete'] and result['all_sampled_states_actions_finite']
    assert actual['physics']['dt'] == 1 / 120
    assert actual['physics']['render_interval'] == 4
    assert config['simulator']['sim']['decimation'] == 4
    robot = config['robot']
    names = robot['kinematic_info']['dof_names']
    bodies = robot['kinematic_info']['body_names']
    controls = robot['control']['control_info']
    assert len(names) == 66 and len(bodies) == 23
    assert robot['control']['control_type'] == 'ControlType.BUILT_IN_PD'
    # Independently resolve the MJCF multi-axis names, then check the instantiated
    # Isaac actuator configuration against the frozen checkpoint's resolved values.
    backend = {}
    offset = 0
    for body in range(23):
        count = len(robot['kinematic_info']['hinge_axes_map'].get(str(body), []))
        group = names[offset:offset + count]
        for axis, name in enumerate(group):
            backend[name] = f'{group[0]}:{axis}' if count > 1 else name
        offset += count
    assert offset == 66 and len(set(backend.values())) == 66
    actuators = actual['scene']['robot']['actuators']
    assert len(actuators) == 1
    actuator = next(iter(actuators.values()))
    assert set(actuator['joint_names_expr']) == set(backend.values())
    fields = [('stiffness', 'stiffness'), ('damping', 'damping'),
              ('armature', 'armature'), ('effort_limit_sim', 'effort_limit'),
              ('velocity_limit_sim', 'velocity_limit')]
    for name in names:
        for actual_key, control_key in fields:
            assert actuator[actual_key][backend[name]] == controls[name][control_key], (name, actual_key)
    for actual_key, control_key in [('p_gains_common', 'stiffness'),
                                    ('d_gains_common', 'damping'),
                                    ('torque_limits_common', 'effort_limit')]:
        assert actual[actual_key] == [controls[n][control_key] for n in names]
    foot_names = ['RightFoot', 'RightToeBase', 'LeftFoot', 'LeftToeBase']
    assert set(actual['contact_sensors']) == set(foot_names)
    checks = []
    for trial in trials:
        count = 0
        contact_frames = dict.fromkeys(foot_names, 0)
        max_speed = 0.0
        min_body_z = math.inf
        root_z = [math.inf, -math.inf]
        max_rotation_error = 0.0
        terminated = False
        previous_motion_time = None
        trace = directory / f"trial-{trial['trial_id']:03d}" / 'trace.jsonl'
        with trace.open() as stream:
            for line in stream:
                row = json.loads(line)
                count += 1
                assert finite(row), (trace, count, 'nonfinite')
                assert row['step'] == count and abs(row['time_seconds'] - count / 30) < 1e-9
                state = row['state']
                for name in ['dof_pos', 'dof_vel', 'dof_forces']:
                    assert len(state[name]) == 1 and len(state[name][0]) == 66
                for name, width in [('rigid_body_pos', 3), ('rigid_body_rot', 4),
                                    ('rigid_body_vel', 3), ('rigid_body_ang_vel', 3)]:
                    assert len(state[name]) == 1 and len(state[name][0]) == 23
                    assert all(len(v) == width for v in state[name][0])
                assert len(row['action_raw'][0]) == len(row['action_processed'][0]) == 66
                motion_time = row['motion_time_seconds'][0]
                if previous_motion_time is not None:
                    assert motion_time > previous_motion_time, (trace, count, 'motion clock reset')
                previous_motion_time = motion_time
                max_speed = max(max_speed, *(math.sqrt(sum(v*v for v in xyz)) for xyz in state['rigid_body_vel'][0]))
                min_body_z = min(min_body_z, *(p[2] for p in state['rigid_body_pos'][0]))
                z = state['rigid_body_pos'][0][0][2]
                root_z = [min(root_z[0], z), max(root_z[1], z)]
                for q in state['rigid_body_rot'][0]:
                    max_rotation_error = max(max_rotation_error, abs(math.sqrt(sum(v*v for v in q)) - 1))
                assert max_rotation_error < 0.001
                for foot in foot_names:
                    force = row['contact_forces'][0][bodies.index(foot)]
                    contact_frames[foot] += int(sum(v*v for v in force) > 1)
                terminated |= bool(row['termination'][0])
        assert count == trial['recorded_frames'] == trial['expected_control_steps']
        assert terminated == (trial['first_termination_step'] is not None)
        checks.append({'trial_id': trial['trial_id'], 'frames': count,
                       'foot_contact_frames_above_1N': contact_frames,
                       'maximum_body_speed_mps': max_speed,
                       'minimum_body_origin_z_m': min_body_z, 'root_z_range_m': root_z,
                       'maximum_rotation_norm_error': max_rotation_error})
    assert sum(c['frames'] for c in checks) == result['recorded_frames']
    return {'artifact_directory': str(directory.relative_to(ROOT)), 'family': result['family'],
            'seed': contract['seed'], 'controller_parameters_match': True,
            'finite_states_actions_contacts': True, 'monotonic_trial_clocks': True,
            'trace_dimensions_and_frame_counts_match': True, 'trials': checks}


def compare(first, second):
    left, right = read(first / 'trials.json'), read(second / 'trials.json')
    assert len(left) == len(right) == 61
    contracts = []
    for directory in (first, second):
        contract = read(directory / 'run-contract.json')
        source_contacts = read(directory / 'resolved-configs.json')['robot']['contact_bodies']
        contract.setdefault('contact_instrumentation', {
            'source_contact_bodies': source_contacts, 'selected_contact_bodies': source_contacts})
        contracts.append(contract)
    assert contracts[0] == contracts[1]
    evaluation_left = read(first / 'evaluation-contract.json')
    evaluation_right = read(second / 'evaluation-contract.json')
    # The original recording serialized component instances as Python reprs;
    # subsequent recordings include function, bindings and static parameters.
    # Both use the same hash-locked sidecar without changing these components.
    assert set(evaluation_left.pop('components')) == set(evaluation_right.pop('components'))
    assert evaluation_left == evaluation_right
    same_labels = all(a['studio_attempt_failed'] == b['studio_attempt_failed'] for a, b in zip(left, right))
    delta = {key: max(abs(a['metrics'][key]['mean'] - b['metrics'][key]['mean'])
                     for a, b in zip(left, right)) for key in left[0]['metrics']}
    identical = 0
    for trial in left:
        path = Path(f"trial-{trial['trial_id']:03d}/trace.jsonl")
        with (first / path).open('rb') as a, (second / path).open('rb') as b:
            identical += hashlib.file_digest(a, 'sha256').digest() == hashlib.file_digest(b, 'sha256').digest()
    return {'same_seed_and_inference_contract': True, 'same_attempt_outcomes': same_labels,
            'maximum_absolute_difference_per_trial_mean_metrics': delta,
            'byte_identical_trace_trials': identical, 'total_trials': len(left),
            'note': 'Physics reruns need not be bit exact; saved poses are the authoritative replay.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    runs = [p.resolve() if p.is_absolute() else ROOT / p for p in args.runs]
    report = {'status': 'passed', 'runs': [audit(p) for p in runs]}
    tracker = [p for p in runs if read(p / 'result.json')['family'] == 'tracker']
    if len(tracker) == 2:
        report['restart_comparison'] = compare(*tracker)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'runs_audited': len(runs),
                      'restart_comparison': report.get('restart_comparison')}))


if __name__ == '__main__':
    main()
