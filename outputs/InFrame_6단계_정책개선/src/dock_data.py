"""Learn goal alignment at training-area approach poses; no goal geometry enters policy inference."""
import math
import numpy as np
from PIL import Image
from common import ROOT,WORK,read,write,block
from teacher import region
from world import World,geo,hd,heading,wrap

def main():
    rng=np.random.default_rng(16851)
    dev={tuple(x) for x in read(ROOT/'학습구역.json')['dev_blocks']}
    w=World('castle',register=False)
    try:
        anchor=w.anchor['C'];cases=[];labels=[];images=[];positions=[]
        near=[p for p in w.grid if hd(p,anchor)<2.9 and region(block(p))=='train' and block(p) not in dev]
        for candidate in near:
            for _ in range(4):
                p=np.array(candidate);p[[0,2]]+=rng.uniform(-.19,.19,2)
                snapped=np.array(w.pf.snap_point(p,w.island))
                if not np.isfinite(snapped).all() or hd(p,snapped)>.13:continue
                if region(block(snapped))!='train' or block(snapped) in dev:continue
                positions.append(snapped)
        for pos in positions:
            dist=min(geo(w.pf,pos,t) for t in w.refs['C'])
            face=heading(pos,anchor);shift=float(rng.uniform(0,2*math.pi/16))
            for j in range(16):
                a=shift+2*math.pi*j/16
                w.reset(pos,a);images.append(np.asarray(Image.fromarray(w.rgb()).resize((80,60),Image.Resampling.BILINEAR)))
                direction=wrap(face-a)
                near_prob=float(np.clip((.85-dist)/.28,0,1));visible=w.visible()['C']
                centered=abs(direction)<math.radians(32.) and visible['pixels']>=140
                labels.append([near_prob,float(centered)*near_prob,math.sin(direction),math.cos(direction),1.])
        np.savez(WORK/'dock.npz',rgb=np.array(images),labels=np.array(labels,np.float32))
        write(ROOT/'정지자료.json',dict(centers=[p.tolist() for p in positions],images=len(images),fit_blocks=sorted({block(p) for p in positions})))
        print(len(positions),len(images))
    finally:w.close()
if __name__=='__main__':main()
