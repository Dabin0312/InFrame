"""Replay untouched Castle PNGs through GetImageSample, H4 and the 4 Hz supervisor."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image

from bridge import MotionGuard, MockSport, FRAME_TTL, MAX_FORWARD, MAX_YAW
from devices import FrontCamera, MockVideo
from multigoal import MultiGoalH4, TWISTS
from runtime import run_session


def sha(rgb):
    return hashlib.sha256(rgb.tobytes()).hexdigest()


def check(directory, key):
    source = json.loads((directory/key/'sim.json').read_text())
    frames = np.stack([np.array(Image.open(directory/key/f'{i}.png').convert('RGB')) for i in range(source['steps'])])
    np.savez_compressed(directory/key/'camera.npz', rgb=frames)
    expected = [step['a'] for step in source['trace']]
    decoded, calls = [], []
    it = iter(frames)
    class VerifiedCamera(FrontCamera):
        def read(self):
            stamp, image = super().read()
            decoded.append(sha(image))
            return stamp, image
    policy = MultiGoalH4(source['prompt'])
    sport = MockSport()
    result = run_session(VerifiedCamera(MockVideo(lambda: next(it)), size=(160,120)), policy,
                         MotionGuard(sport, emit=calls.append))
    rows = []
    for i,(image, action) in enumerate(zip(frames, expected)):
        observed = policy.actions[i] if i<len(policy.actions) else None
        rows.append(dict(step=i+1,sim=action,mock=observed,rgb_sha256=sha(image),
                         same_rgb=i<len(decoded) and decoded[i]==sha(image)))
    movements = [e for e in calls if e['rpc']=='Move']
    raw = [e['raw'] for e in movements]
    stop = next((i+1 for i,a in enumerate(policy.actions) if a==3), None)
    same = sum(r['same_rgb'] and r['sim']==r['mock'] for r in rows)
    assert len(movements)==len(expected)-1 and all(e['seq']==i and e['raw']==list(TWISTS[a])
        for i,(e,a) in enumerate(zip(movements, expected[:-1]))), (key,result,len(movements))
    assert same==len(rows)==len(policy.actions) and stop==source['steps'] and source['success'], (key, result, same)
    assert result['reason']=='goal_stop' and result['stop_confirmed'] and sport.twist==(0,0,0)
    assert all(0<=e['args'][0]<=MAX_FORWARD and e['args'][1]==0 and abs(e['args'][2])<=MAX_YAW for e in movements)
    return dict(goal=source['prompt'],layout=source['layout'],start=source['start'],steps=len(rows),matched=same,
                sim_stop=source['steps'],mock_stop=stop,audit=source['audit'],final_rpc=calls[-1]['rpc'],
                max_request=[max(a[0] for a in raw),max(abs(a[1]) for a in raw)],
                max_sent=[max(e['args'][0] for e in movements),max(abs(e['args'][2]) for e in movements)],
                trace=rows)


def cut(directory, key='bin'):
    source = json.loads((directory/key/'sim.json').read_text())
    first_move = next(i for i,step in enumerate(source['trace']) if step['a']==0)
    frames = [np.array(Image.open(directory/key/f'{i}.png').convert('RGB')) for i in range(first_move+1)]
    it = iter(frames)
    def feed():
        image = next(it, None)
        if image is None:
            time.sleep(FRAME_TTL+.12)
            return frames[-1]
        return image
    events = []
    sport = MockSport()
    guard = MotionGuard(sport, emit=events.append)
    model = MultiGoalH4(source['prompt'])
    result = run_session(FrontCamera(MockVideo(feed),size=(160,120)),model,guard)
    time.sleep(FRAME_TTL+.13)  # the blocked read has returned; watch for a late Move
    last = events[-2]
    assert last['rpc']=='Move' and last['args'][0]>0 and events[-1]['rpc']=='StopMove'
    delay = events[-1]['t']-last['captured']
    assert result['reason']=='frame_timeout' and result['stop_confirmed'] and sport.twist==(0,0,0)
    assert FRAME_TTL<=delay<FRAME_TTL+.08
    return dict(reason=result['reason'],last_move=last['args'],delay_s=delay,final_twist=sport.twist,
                actions_after_timeout=sum(e['rpc']=='Move' and e['t']>=events[-1]['t'] for e in events))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path)
    directory=p.parse_args().directory
    checks=[]
    for key in ('chair','bin','extinguisher'):
        r=check(directory,key);checks.append(r);print(key,r['matched'],r['mock_stop'],flush=True)
    assert len({r['trace'][0]['rgb_sha256'] for r in checks})==1
    output=dict(cases=checks,camera_cut=cut(directory))
    (directory/'parity.json').write_text(json.dumps(output,indent=2)+'\n')
    print(output['camera_cut'])
