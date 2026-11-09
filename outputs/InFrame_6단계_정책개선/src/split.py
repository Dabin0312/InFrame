"""Seal untouched starts by geometry alone, before any new policy rollout."""
from collections import Counter,defaultdict
import math
import numpy as np
from scipy.spatial import cKDTree
from common import ROOT,S4,S5,WORK,read,write,sha,block
from teacher import region
from world import World

def select(w, groups, n, tag, seed, train=False):
    rng=np.random.default_rng(seed);groups={b:list(v) for b,v in groups.items()}
    order=sorted(groups);rng.shuffle(order)
    for b in order:rng.shuffle(groups[b])
    out=[]
    while len(out)<n:
        usable=False
        for b in order:
            if not groups[b]:continue
            usable=True
            i=groups[b].pop();p=w.grid[i]
            yaw=float(rng.uniform(-math.pi,math.pi))
            out.append(dict(id=f'{tag}-{len(out):03}',scene='castle',goal_text='소화기',start_xyz=p.tolist(),start_yaw=yaw,block=list(b)))
            if len(out)==n:break
        if not usable:raise RuntimeError(f'{tag} has only {len(out)} starts')
    return out

def main():
    w=World('castle',register=False)
    try:
        old=[x for x in read(S4/'manifest.json') if x['scene']=='castle']
        past_starts=np.array([r['start_xyz'] for r in old])[:,[0,2]]
        trajectories=[]
        for r in old:
            trajectories.append(np.array([__import__('json').loads(l)['xyz'] for l in (S4/'episodes'/r['id']/'actions.jsonl').read_text().splitlines()])[:,[0,2]])
        for path in (S5/'episodes').glob('*/*/steps.jsonl'):
            trajectories.append(np.array([__import__('json').loads(l)['xyz'] for l in path.read_text().splitlines()])[:,[0,2]])
        prior=cKDTree(np.concatenate(trajectories));starts=cKDTree(past_starts)
        groups=defaultdict(list);training=defaultdict(list)
        for i,p in enumerate(w.grid):
            if not np.isfinite(w.ds[:,i]).any() or w.ds[:,i].min()<2:continue
            b=block(p);xz=p[[0,2]]
            if region(b)=='reserved' and prior.query(xz)[0]>=.16:groups[b].append(i)
            if region(b)=='train' and starts.query(xz)[0]>.12:training[b].append(i)
        train_keys=[b for b in sorted(training) if len(training[b])>=6]
        rng=np.random.default_rng(61035);rng.shuffle(train_keys)
        dev_keys=set(train_keys[:11]);build={b:v for b,v in training.items() if b not in dev_keys}
        test=select(w,groups,60,'FRESH',86127)
        dev=select(w,{b:training[b] for b in dev_keys},72,'DEV',61110)
        harvest=select(w,build,132,'LEARN',61120)
        assert not {tuple(x['block']) for x in test}&{block(r['start_xyz']) for r in old}
        info=dict(seed=86127,selection='Uniform shuffled candidates within reserved 2 m blocks, sampled round-robin, min 0.16 m from prior recorded teacher/student positions. Yaw uniform.',dt=.25,collision_limit=3,timeout_s=150,goal_radius_m=.8,
                    cases=test,blocks=len({tuple(x['block']) for x in test}),min_prior_trace_m=min(float(prior.query(np.array(x['start_xyz'])[[0,2]])[0]) for x in test),
                    min_prior_start_m=min(float(starts.query(np.array(x['start_xyz'])[[0,2]])[0]) for x in test))
        path=ROOT/'봉인_출발점.json'
        if path.exists():assert read(path)==info,'Existing holdout differs'
        else:write(path,info)
        write(ROOT/'학습구역.json',dict(dev_blocks=sorted(dev_keys),train_cases=harvest,dev_cases=dev,holdout_sha256=sha(path)))
        print('sealed',len(test),info['blocks'],info['min_prior_trace_m'],info['min_prior_start_m'],sha(path))
    finally:w.close()
if __name__=='__main__':main()
