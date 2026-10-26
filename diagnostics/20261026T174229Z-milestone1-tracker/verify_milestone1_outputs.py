"""Independent CPU video/trace completeness check after the Isaac process exits."""
import json
from pathlib import Path
import imageio.v2 as imageio

root=Path('/studio/output')
trials=json.loads((root/'trials.json').read_text())
result=json.loads((root/'result.json').read_text())
validated=[]
for trial in trials:
    directory=root/f"trial-{trial['trial_id']:03d}"
    reader=imageio.get_reader(str(directory/'performance.mp4'))
    try:
        count=reader.count_frames()
        metadata=reader.get_meta_data()
        first=reader.get_data(0)
        last=reader.get_data(count-1)
    finally:
        reader.close()
    expected=trial['expected_control_steps']
    with (directory/'trace.jsonl').open() as stream:
        trace_count=sum(1 for _ in stream)
    assert trial['complete'] and trial['recorded_frames']==count==trace_count==expected
    assert abs(metadata['fps']-30)<0.001
    assert first.shape==last.shape==(480,640,3)
    validated.append({'trial_id':trial['trial_id'],'decoded_frame_count':count,
                      'trace_samples':trace_count,'fps':metadata['fps'],'shape':list(first.shape)})
assert len(validated)==result['trials']
assert sum(t['decoded_frame_count'] for t in validated)==result['recorded_frames']
(root/'media-validation.json').write_text(json.dumps({'status':'passed','trials':validated},indent=2)+'\n')
print(f'Validated {len(validated)} complete videos and traces.')
