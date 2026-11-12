"""Exercise the original and transfer ONNX motion memories on real Castle RGB pairs."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from multigoal import PROJECT, encode_goal, session, visual_change


def main(directory):
    policies=[session(str(PROJECT/'h4nav'/f'{name}-h4.onnx')) for name in ('escape','transfer')]
    embeddings={name:encode_goal(name) for name in ('chair','trash can','fire extinguisher')}
    records=[]
    def test(a,b,goal):
        small=lambda f:cv2.resize(f,(80,60),interpolation=cv2.INTER_AREA)
        prev,curr=small(a),small(b)
        # Replay one commanded forward with zero initial stall count. Index 11
        # of next_escape_memory is the graph's actual accumulated stall counter.
        inputs=dict(camera=b[None],rgb=np.stack([prev]*3+[curr])[None],goal_embedding=embeddings[goal],
                    rgb_goal_proposals=np.zeros((1,4,5),np.float32),previous_action=np.array([[0,1,0,0]],np.float32),
                    memory=np.zeros((1,1,44),np.float32),search_memory=np.zeros((1,9),np.float32),
                    escape_memory=np.zeros((1,20),np.float32))
        flags=[]
        change=visual_change(prev,curr)
        for i,policy in enumerate(policies):
            if i:inputs['visual_change']=np.array([[change,change,change,0]],np.float32)
            mem=policy.run(['next_escape_memory'],inputs)[0]
            flags.append(bool(mem[0,11]<.5))
        return flags
    for key in ('chair','bin','extinguisher'):
        src=json.loads((directory/key/'sim.json').read_text())
        img=lambda i: np.array(Image.open(directory/key/f'{i}.png').convert('RGB'))
        for i in sorted({0,len(src['trace'])//2,len(src['trace'])-1}):
            a=img(i)
            for name,gain,bias,gamma in [('offset +12',1,12,1),('offset -15',1,-15,1),('gain 1.3',1.3,5,1),
                                          ('gain 0.72',.72,-4,1),('gamma 0.75',1,0,.75),('gamma 1.4',1,0,1.4)]:
                b=np.clip(np.rint((a/255.)**gamma*255*gain+bias),0,255).astype(np.uint8)
                flags=test(a,b,src['prompt']);records.append(dict(goal=key,step=i+1,kind='stationary',exposure=name,advanced=flags))
        for i,(p,q) in enumerate(zip(src['trace'],src['trace'][1:])):
            if p['a']==0 and np.hypot(p['x']-q['x'],p['z']-q['z'])>.21:
                flags=test(img(i),img(i+1),src['prompt']);records.append(dict(goal=key,step=i+1,kind='translated',advanced=flags))
    summary={}
    for kind in ('stationary','translated'):
        rows=[r for r in records if r['kind']==kind]
        summary[kind]=dict(pairs=len(rows),old_advanced=sum(r['advanced'][0] for r in rows),new_advanced=sum(r['advanced'][1] for r in rows))
    (directory/'exposure.json').write_text(json.dumps(dict(summary=summary,records=records),indent=2))
    print(summary)
    assert summary['stationary']['new_advanced']==0 and summary['translated']['new_advanced']==summary['translated']['pairs']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);main(parser.parse_args().directory)
