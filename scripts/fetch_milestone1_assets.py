#!/usr/bin/env python3
"""Stage only pinned M1 assets; verify LFS payloads against committed SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'vendor/ProtoMotions'
REV = 'f69fdcaabff31846b4d2247207417b57dc788828'
DEST = ROOT / '.runtime/milestone1/assets'

def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args])

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-motion-data', action='store_true',
                        help='Include BONES-SEED samples only after dataset eligibility/license is confirmed.')
    args = parser.parse_args()
    assert git('rev-parse', 'HEAD').decode().strip() == REV
    paths = git('ls-tree', '-r', '--name-only', REV).decode().splitlines()
    model_dirs = ['data/pretrained_models/motion_tracker/soma-bones/',
                  'data/pretrained_models/gpc_prior/soma_bones/']
    selected = []
    for path in paths:
        name = Path(path).name
        model = any(path.startswith(p) for p in model_dirs)
        if (model and name in {'last_lab.ckpt', 'inference_last.ckpt',
                'resolved_configs.pt', 'resolved_configs_inference.pt',
                'resolved_configs.yaml', 'resolved_configs_inference.yaml',
                'MODEL_CARD.md', 'LICENSE.pdf', 'NOTICE.txt', 'experiment_config.py', 'config.yaml'}
            or path in {'data/motion_for_trackers/soma23_bones_seed_mini.pt',
                        'data/motion_for_trackers/crouch_soma23.pt',
                        'protomotions/data/assets/mjcf/soma23_humanoid.xml', 'LICENSE.md'}
            or path.startswith(('protomotions/data/assets/usd/', 'protomotions/data/assets/checkerboard/', 'legal/'))):
            selected.append(path)
    records = []
    for path in selected:
        if path.startswith('data/motion_for_trackers/') and not args.include_motion_data:
            continue
        data = git('show', f'{REV}:{path}')
        target = DEST / path
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f'https://github.com/NVlabs/ProtoMotions/blob/{REV}/{path}'
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            fields = dict(line.split(' ', 1) for line in data.decode().splitlines())
            expected = fields['oid'].removeprefix('sha256:')
            size = int(fields['size'])
            url = f'https://media.githubusercontent.com/media/NVlabs/ProtoMotions/{REV}/{path}'
            if not target.exists() or target.stat().st_size != size or digest(target) != expected:
                print(f'Downloading {path} ({size} bytes)', flush=True)
                partial = target.with_name(target.name + '.partial')
                with urllib.request.urlopen(url, timeout=300) as response, partial.open('wb') as out:
                    shutil.copyfileobj(response, out, 8 * 1024 * 1024)
                assert partial.stat().st_size == size, path
                assert digest(partial) == expected, path
                partial.replace(target)
            kind = 'git-lfs-sha256'
        else:
            expected = hashlib.sha256(data).hexdigest()
            size = len(data)
            target.write_bytes(data)
            kind = 'pinned-git-blob'
        records.append({'path': path, 'sha256': expected, 'bytes': size,
                        'verification': kind, 'source_url': url})
    manifest = {'revision': REV, 'asset_root': str(DEST.relative_to(ROOT)), 'files': records,
                'motion_data_included': args.include_motion_data,
                'provenance_note': 'At this revision last_lab.ckpt and last.ckpt have identical LFS OIDs; no separate fine-tune identity can be established.'}
    (ROOT / 'config/milestone1-assets.lock.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Verified {len(records)} files; manifest: config/milestone1-assets.lock.json', flush=True)

if __name__ == '__main__':
    main()
