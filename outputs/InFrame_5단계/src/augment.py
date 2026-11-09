"""Render three camera-heading variants of each training demonstration, at the original positions."""
from pathlib import Path
import json,sys,argparse
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'InFrame_4단계'
sys.path.insert(0,str(PRIOR/'src'))
from world import World

def main(out):
    names=json.loads((ROOT/'training_data.json').read_text())['train_ids']
    assert len(names)==297 and all(k.startswith('C-train-') for k in names)
    w=World('castle',register=False);rng=np.random.default_rng(7351)
    try:
        out.mkdir(parents=True,exist_ok=True)
        for ep in names:
            rows=[json.loads(line) for line in (PRIOR/'episodes'/ep/'actions.jsonl').read_text().splitlines()]
            offsets=[];images=[]
            for bound in [.45,1.3,np.pi]:
                # Smooth changes retain valid four-frame time order.
                knots=np.arange(0,len(rows)+16,16)
                delta=np.interp(np.arange(len(rows)),knots,rng.uniform(-bound,bound,len(knots)))
                offsets.append(delta)
                seq=[]
                for row,angle in zip(rows,delta):
                    w.reset(np.asarray(row['xyz']),row['yaw']+angle)
                    seq.append(np.asarray(Image.fromarray(w.rgb()).resize((80,60),Image.Resampling.BILINEAR)))
                images.append(seq)
            np.savez(out/(ep+'.npz'),offsets=offsets,images=np.asarray(images),actions=[r['action'] for r in rows])
    finally:w.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);main(p.parse_args().out)
