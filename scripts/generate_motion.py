#!/usr/bin/env python3
"""Generate a SOMA-77 motion clip from text with the pinned local Kimodo-SOMA-RP-v1.2 model.

Writes into --output: motion.npz (Kimodo NPZ, somaskel77 at 30 fps), generation.json, generate.log.
Refuses to run when config/kimodo.lock.json does not match the files on disk, or when another
studio GPU job (studio-* container or the studio GPU lock) is active.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'config/kimodo.lock.json'
VENV_PYTHON = ROOT / '.runtime/kimodo/venv/bin/python'
MODELS = ROOT / '.runtime/kimodo/models'
GPU_LOCK = ROOT / '.runtime/studio-gpu.lock'
MODEL = 'Kimodo-SOMA-RP-v1.2'

# Runs inside the kimodo venv: generation, then a small JSON report on stdout's last line.
RUNNER = r'''
import json, sys, torch
from kimodo.scripts import generate
from kimodo.skeleton.definitions import SOMASkeleton77
npz_path = sys.argv[2]
sys.argv = ['kimodo_gen'] + json.loads(sys.argv[1])
generate.main()
import numpy as np
data = np.load(npz_path)
root = data['posed_joints'][:, 0, :]
report = {'torch': torch.__version__, 'joint_names': [n for n, _ in SOMASkeleton77.bone_order_names_with_parents],
          'npz': {k: list(data[k].shape) for k in data.files},
          'finite': bool(all(np.isfinite(data[k]).all() for k in data.files)),
          'root': {k: [float(v) for v in f(root, axis=0)] for k, f in (('mean_xyz', np.mean), ('min_xyz', np.min), ('max_xyz', np.max))}}
if torch.cuda.is_available():
    report['gpu_name'] = torch.cuda.get_device_name(0)
    report['gpu_peak_allocated_bytes'] = torch.cuda.max_memory_allocated(0)
    report['gpu_peak_reserved_bytes'] = torch.cuda.max_memory_reserved(0)
print('KIMODO_REPORT ' + json.dumps(report))
'''


def fail(message):
    print(f'generate_motion: {message}', file=sys.stderr)
    sys.exit(1)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_lock():
    if not LOCK.exists():
        fail(f'lock file missing: {LOCK}')
    lock = json.loads(LOCK.read_text())
    if not VENV_PYTHON.exists():
        fail(f'kimodo venv missing: {VENV_PYTHON} (see docs/MOTION_GENERATION.md)')
    code = ROOT / lock['code']['checkout']
    head = subprocess.run(['git', '-C', str(code), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    if head.returncode != 0 or head.stdout.strip() != lock['code']['commit']:
        fail(f"{code} is not at the locked commit {lock['code']['commit']}")
    for entry in lock['weights']:
        base = ROOT / entry['local_dir']
        for record in entry['files']:
            path = base / record['path']
            if not path.exists():
                fail(f'locked file missing: {path} (run scripts/fetch_kimodo_weights.py)')
            if path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
                fail(f'locked file does not match config/kimodo.lock.json: {path}')
    return lock


def studio_containers():
    result = subprocess.run([str(ROOT / 'scripts/docker.sh'), 'ps', '--format', '{{.Names}}'],
                            capture_output=True, text=True)
    return [n for n in result.stdout.split() if n.startswith('studio-')]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--seconds', type=float, default=4.0)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--steps', type=int, default=100, help='diffusion steps (Kimodo default 100)')
    parser.add_argument('--cfg-weight', type=float, default=None,
                        help='regular CFG weight; default keeps the model setting (separated, [2.0, 2.0])')
    parser.add_argument('--device', default='cuda', help="cuda, cuda:N or cpu")
    args = parser.parse_args()
    if not 0 < args.seconds <= 10:
        fail('--seconds must be in (0, 10]')
    lock = verify_lock()
    if (weights := [w for w in lock['weights'] if w['repo_id'].endswith(MODEL)]) == []:
        fail(f'{MODEL} is not in the lock file')

    args.output.mkdir(parents=True, exist_ok=True)
    out_npz = args.output / 'motion.npz'
    if out_npz.exists():
        fail(f'{out_npz} already exists')
    GPU_LOCK.parent.mkdir(parents=True, exist_ok=True)
    gpu_lock = open(GPU_LOCK, 'w')
    try:
        fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fail('another studio GPU job holds .runtime/studio-gpu.lock')
    if running := studio_containers():
        fail(f'studio container(s) running: {", ".join(running)}; one heavy GPU job at a time')

    kimodo_args = [args.prompt, '--model', MODEL, '--duration', str(args.seconds), '--seed', str(args.seed),
                   '--diffusion_steps', str(args.steps), '--num_samples', '1', '--output', str(out_npz)]
    if args.cfg_weight is not None:
        kimodo_args += ['--cfg_type', 'regular', '--cfg_weight', str(args.cfg_weight)]
    env = dict(os.environ, CHECKPOINT_DIR=str(MODELS), TEXT_ENCODERS_DIR=str(MODELS / 'text_encoder'),
               TEXT_ENCODER_MODE='local', LOCAL_CACHE='True', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               PYTHONUNBUFFERED='1')
    if args.device == 'cpu':
        env['CUDA_VISIBLE_DEVICES'] = ''
        env['TEXT_ENCODER_DEVICE'] = 'cpu'
    elif args.device.startswith('cuda:'):
        env['CUDA_VISIBLE_DEVICES'] = args.device.split(':', 1)[1]
    elif args.device != 'cuda':
        fail(f'unknown --device {args.device}')

    command = [str(VENV_PYTHON), '-c', RUNNER, json.dumps(kimodo_args), str(out_npz)]
    started = dt.datetime.now(dt.timezone.utc)
    clock = time.monotonic()
    report = None
    with (args.output / 'generate.log').open('w') as log:
        log.write(f'# {started.isoformat()} cwd={ROOT}\n# kimodo args: {json.dumps(kimodo_args)}\n')
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True)
        for line in process.stdout:
            log.write(line)
            if line.startswith('KIMODO_REPORT '):
                report = json.loads(line[len('KIMODO_REPORT '):])
            else:
                sys.stdout.write(line)
        code = process.wait()
    wall = time.monotonic() - clock
    if code != 0 or report is None:
        fail(f'kimodo exited with code {code}; see {args.output / "generate.log"}')
    if not out_npz.exists():
        fail(f'kimodo did not write {out_npz}')

    frames = int(args.seconds * lock['fps'])
    shapes = report['npz']
    if shapes.get('posed_joints') != [frames, 77, 3] or shapes.get('local_rot_mats') != [frames, 77, 3, 3]:
        fail(f'unexpected npz shapes: {shapes}')
    if not report['finite']:
        fail('motion.npz contains non-finite values')
    if report['joint_names'] != lock['joint_names']:
        fail('kimodo joint order differs from the locked SOMASKEL77 order')
    root_mean = report['root']['mean_xyz']
    up_axis = max(range(3), key=lambda i: abs(root_mean[i]))
    height = root_mean[up_axis]
    generation = {
        'prompt': args.prompt, 'seconds': args.seconds, 'frames': frames, 'fps': lock['fps'], 'seed': args.seed,
        'diffusion_steps': args.steps,
        'cfg': {'cfg_type': 'regular', 'cfg_weight': args.cfg_weight} if args.cfg_weight is not None
               else {'cfg_type': 'separated', 'cfg_weight': [2.0, 2.0], 'source': 'model default'},
        'post_processing': True, 'device': args.device,
        'model': {'id': weights[0]['repo_id'], 'revision': weights[0]['revision'],
                  'weights_sha256': next(f['sha256'] for f in weights[0]['files'] if f['path'] == 'model.safetensors')},
        'text_encoder': [{'repo_id': w['repo_id'], 'revision': w['revision']} for w in lock['weights']
                         if 'text_encoder' in w['local_dir']],
        'kimodo_commit': lock['code']['commit'], 'torch': report['torch'],
        'gpu_name': report.get('gpu_name'), 'gpu_peak_allocated_bytes': report.get('gpu_peak_allocated_bytes'),
        'gpu_peak_reserved_bytes': report.get('gpu_peak_reserved_bytes'),
        'wall_clock_seconds': round(wall, 2), 'started_utc': started.isoformat(),
        'npz': shapes, 'skeleton': lock['skeleton'], 'joint_names': report['joint_names'],
        'root': dict(report['root'], up_axis='xyz'[up_axis], mean_height=height,
                     units='metres (assumed; SOMA rest pelvis is about 0.95 m)', height_plausible=0.5 <= height <= 1.3),
    }
    (args.output / 'generation.json').write_text(json.dumps(generation, indent=2) + '\n')
    print(f'wrote {out_npz} ({frames} frames, 77 joints, up axis {generation["root"]["up_axis"]}, '
          f'root height {height:.3f}) in {wall:.1f}s')


if __name__ == '__main__':
    main()
