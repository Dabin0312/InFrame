"""Acquire RGB and teacher correction labels only inside designated training blocks."""
from collections import Counter
import json,math
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from common import ROOT,S4,WORK,read,write,block
from teacher import region
from world import World,driveable,heading,wrap,hd
ANGLE_COUNT=24
ANGLES=np.arange(ANGLE_COUNT)*2*math.pi/ANGLE_COUNT
RELATIVE=np.array([-90,-60,-45,-30,-15,0,15,30,45,60,90])
DISTANCE=.72

def rays(w,pos):
    out=[]
    for theta in ANGLES:
        direction=np.array([-math.sin(theta),0.,-math.cos(theta)])
        cur=pos.copy()
        for _ in range(9):
            desired=cur+direction*.08
            after=np.asarray(w.pf.try_step_no_sliding(cur,desired))
            length=hd(cur,after);cur=after
            if length<.0785:break
        out.append(min(DISTANCE,hd(pos,cur)))
    return np.array(out)

def guide(w,tree,pos):
    near=tree.query(pos[[0,2]],k=18)[1]
    options=sorted(near,key=lambda i: hd(pos,w.grid[i])+w.ds[:,i].min())
    for node in options:
        if np.isfinite(w.ds[:,node]).any() and driveable(w.pf,pos,w.grid[node]):break
    else:return None
    path,_=w.route('C',node)
    chain=np.vstack((pos,path));left=.88;waypoint=chain[-1]
    distance=sum(hd(a,b) for a,b in zip(chain,chain[1:]))
    if distance<.58:return heading(pos,w.anchor['C']),distance
    for a,b in zip(chain,chain[1:]):
        segment=hd(a,b)
        if left<segment:
            waypoint=a+(b-a)*(left/segment);break
        left-=segment
    return heading(pos,waypoint),distance

def main():
    spec=read(ROOT/'학습구역.json');dev={tuple(b) for b in spec['dev_blocks']}
    allowed=lambda p:region(block(p))=='train' and block(p) not in dev
    rng=np.random.default_rng(61132);w=World('castle',register=False)
    try:
        tree=cKDTree(w.grid[:,[0,2]])
        stats=Counter();examples={};filtered=Counter();positions=[]
        baseline=read(WORK/'train/before.json')
        for r in baseline:
            if r['success']:continue
            id=r['start_id'];log=[json.loads(s) for s in (WORK/'train/before'/id/'steps.jsonl').read_text().splitlines()]
            if r['reason']=='collision_limit':
                event=next(i for i,v in enumerate(log) if v['collision'])
                kind='boundary'
            else:
                end_actions=[v['action'] for v in log[-81:-1]]
                flips=sum(a[1]*b[1]<0 for a,b in zip(end_actions,end_actions[1:]))
                stationary=max(hd(v['xyz'],log[-1]['xyz']) for v in log[-81:])<.12
                if not stationary or flips<12:continue
                event=len(log)-2;kind='rotation'
            event_pos=np.array(log[event]['xyz'])
            if not allowed(event_pos):filtered[kind]+=1;continue
            stats[kind]+=1
            examples.setdefault(kind,[]).append(dict(id=id,t=event,pos=event_pos.tolist(),commands=r['commands'],meters=r['travel_m'],end_reason=r['reason']))
            for t in sorted({max(0,event-8),max(0,event-4),event,min(event+1,len(log)-1)}):
                p=np.array(log[t]['xyz'])
                if allowed(p):positions.append((p,'failure'))
            for _ in range(18):
                query=event_pos.copy();query[[0,2]]+=rng.normal(0,.32,2)
                p=np.array(w.pf.snap_point(query,w.island))
                if np.isfinite(p).all() and hd(p,query)<.08 and allowed(p):positions.append((p,'failure_neighborhood'))
        assert stats['boundary'] and stats['rotation']
        valid=[p for i,p in enumerate(w.grid) if allowed(p) and np.isfinite(w.ds[:,i]).any()]
        for pos in valid:
            positions.append((np.array(pos),'train_grid'))
            if w.pf.distance_to_closest_obstacle(pos)<.48:
                query=np.array(pos);query[[0,2]]+=rng.normal(0,.24,2)
                near=np.array(w.pf.snap_point(query,w.island))
                if np.isfinite(near).all() and hd(near,query)<.21 and allowed(near):
                    positions.append((near,'edge'))
        rng.shuffle(positions);visited=set();images=[];labels=[];origins=[];kinds=Counter()
        rows=[]
        for pos,kind in positions:
            key=tuple(np.round(pos[[0,2]]/.035).astype(int))
            if key in visited:continue
            expert=guide(w,tree,pos)
            if expert is None:continue
            visited.add(key);theta,dist=expert
            sweep=rays(w,pos);idx0=int(rng.integers(2))
            bearings=list(range(idx0,ANGLE_COUNT,2))
            if kind.startswith('failure') or kind=='edge':bearings=list(range(ANGLE_COUNT))
            for y in bearings:
                w.reset(pos,ANGLES[y])
                img=w.rgb()
                images.append(np.asarray(Image.fromarray(img).resize((80,60),Image.Resampling.BILINEAR)))
                a=wrap(theta-ANGLES[y])
                labels.append([math.sin(a),math.cos(a),math.log1p(dist),*(sweep[(y+(RELATIVE//15))%ANGLE_COUNT]/DISTANCE)])
                origins.append(len(rows))
            rows.append(dict(x=float(pos[0]),z=float(pos[2]),block=list(block(pos)),kind=kind))
            kinds[kind]+=1
        np.savez(WORK/'corrections.npz',rgb=np.stack(images),labels=np.asarray(labels,np.float32),origin=np.array(origins,np.int32))
        write(ROOT/'교정자료.json',dict(positions=rows,images=len(images),position_types=kinds,reproduced_inside_training=stats,excluded_outside_fit_blocks=filtered,examples=examples))
        print('collected',len(rows),len(images),stats,kinds,flush=True)
    finally:w.close()
if __name__=='__main__':main()
