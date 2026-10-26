"""Inspect complete bundled motion durations on CPU in the pinned image."""
import json
from pathlib import Path
import torch
from protomotions.components.motion_lib import MotionLib
assets=Path('/studio/assets')
config=torch.load(assets/'data/pretrained_models/motion_tracker/soma-bones/resolved_configs_inference.pt',map_location='cpu',weights_only=False)
summary={}
for name in ('soma23_bones_seed_mini.pt','crouch_soma23.pt'):
    cfg=config['motion_lib']
    cfg.motion_file=str(assets/'data/motion_for_trackers'/name)
    cfg.motion_file_shard_indices=None
    lib=MotionLib(config=cfg,device=torch.device('cpu'))
    lengths=lib.get_motion_length(None)
    summary[name]={'num_motions':lib.num_motions(),'motion_lengths_seconds':lengths.tolist(),
        'reference_frames':lib.get_motion_num_frames(None).tolist(),
        'control_steps_30hz':(lengths/(1/30)).floor().long().tolist(),
        'total_seconds':float(lengths.sum()),'maximum_seconds':float(lengths.max())}
Path('/studio/output/motion-inventory.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
