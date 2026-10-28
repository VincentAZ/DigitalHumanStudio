#!/usr/bin/env python3
"""Download the pinned Kimodo-SOMA-RP-v1.2 weights and text-encoder repos; write config/kimodo.lock.json.

Run with the kimodo venv: .runtime/kimodo/venv/bin/python scripts/fetch_kimodo_weights.py
No Hugging Face token is used or stored. See docs/MOTION_GENERATION.md for the licence steps.
"""
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / '.runtime/kimodo/models'
LOCK = ROOT / 'config/kimodo.lock.json'
LICENCE_DIR = ROOT / 'docs/licences/kimodo'
CODE_REPO = 'https://github.com/nv-tlabs/kimodo'
MNTP = 'McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp'
REPOS = [
    # repo id, pinned commit, local subdirectory, licence name, licence file
    ('nvidia/Kimodo-SOMA-RP-v1.2', '0e3c89024d896064b6851201373f7834784a386b',
     'Kimodo-SOMA-RP-v1.2', 'NVIDIA Open Model License', 'LICENSE'),
    (MNTP, '31474e395ada192e8ed1586db6be79fb3b70c9c0', f'text_encoder/{MNTP}', 'MIT (per model card)', None),
    (f'{MNTP}-supervised', 'baa8ebf04a1c2500e61288e7dad65e8ae42601a7', f'text_encoder/{MNTP}-supervised',
     'MIT (per model card)', None),
    # Byte-identical mirror of the gated meta-llama/Meta-Llama-3-8B-Instruct shards (SHA-256 checked
    # against Meta's public repo metadata, see docs/MOTION_GENERATION.md). Llama 3 Community License.
    ('NousResearch/Meta-Llama-3-8B-Instruct', '53346005fb0ef11d3b6a83b12c895cca40156b6c',
     'text_encoder/NousResearch/Meta-Llama-3-8B-Instruct', 'Meta Llama 3 Community License', 'LICENSE'),
]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    MODELS.mkdir(parents=True, exist_ok=True)
    weights = []
    for repo, rev, sub, licence, licence_file in REPOS:
        local = MODELS / sub
        snapshot_download(repo_id=repo, revision=rev, local_dir=str(local), token=False,
                          ignore_patterns=['original/*'])
        entry = {'repo_id': repo, 'revision': rev, 'local_dir': str(local.relative_to(ROOT)),
                 'licence': licence, 'files': []}
        if licence_file:
            entry['licence_sha256'] = sha256(local / licence_file)
        if sub.endswith('-mntp'):
            # The LoRA adapter names the gated base repo; point it at the pinned local mirror instead.
            config = local / 'adapter_config.json'
            data = json.loads(config.read_text())
            entry['patched'] = {'file': 'adapter_config.json', 'original_sha256': sha256(config),
                                'base_model_name_or_path': data['base_model_name_or_path']}
            data['base_model_name_or_path'] = str(MODELS / 'text_encoder/NousResearch/Meta-Llama-3-8B-Instruct')
            config.write_text(json.dumps(data, indent=2) + '\n')
        for path in sorted(p for p in local.rglob('*') if p.is_file() and '.cache' not in p.parts):
            entry['files'].append({'path': str(path.relative_to(local)), 'bytes': path.stat().st_size,
                                   'sha256': sha256(path)})
        weights.append(entry)
    kimodo = MODELS / 'Kimodo-SOMA-RP-v1.2'
    LICENCE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ('LICENSE', 'README.md'):
        (LICENCE_DIR / name).write_bytes((kimodo / name).read_bytes())
    (LICENCE_DIR / 'LICENSE-Llama3-Community').write_bytes(
        (MODELS / 'text_encoder/NousResearch/Meta-Llama-3-8B-Instruct/LICENSE').read_bytes())
    commit = subprocess.check_output(['git', '-C', str(ROOT / 'vendor/kimodo'), 'rev-parse', 'HEAD']).decode().strip()
    lock = {
        'code': {'repo': CODE_REPO, 'commit': commit, 'licence': 'Apache-2.0', 'checkout': 'vendor/kimodo'},
        'model': 'Kimodo-SOMA-RP-v1.2',
        'skeleton': 'somaskel77',
        'fps': 30,
        'joint_names': [],  # filled below from the pinned code
        'weights': weights,
        'download_date': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    from kimodo.skeleton.definitions import SOMASkeleton77
    lock['joint_names'] = [name for name, _ in SOMASkeleton77.bone_order_names_with_parents]
    LOCK.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'wrote {LOCK}')


if __name__ == '__main__':
    main()
