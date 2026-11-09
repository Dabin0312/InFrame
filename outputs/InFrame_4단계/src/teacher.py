"""Deterministic map teacher. RGB(t), command(t) -> pose(t+1), with a separate terminal observation."""
from world import *
import argparse,hashlib,time,collections
from PIL import Image

def region(cell):
    n=int.from_bytes(hashlib.sha256(f'InFrame4/{cell[0]}/{cell[1]}'.encode()).digest()[:4],'big')%10
    return 'reserved' if n==0 else 'val' if n in (1,2) else 'train'
def tasks(w):
    cases=[];rng=np.random.default_rng(4702)
    if not w.wide:
        for j,i in enumerate(range(0,33,3)):
            for k in ['A','B']:cases.append(dict(id=f'F-{k}-{j:02}',i=i,k=k,yaw=float(rng.uniform(-math.pi,math.pi)),split='near',block='fire',mode='teacher'))
        for k in ['A','B']:
            c=next(c for c in cases if c['k']==k);cases.append(dict(c,id='X-F-'+k,split='control',mode='look_away',paired=c['id']))
        return cases
    ids=np.flatnonzero(np.isfinite(w.ds.min(0))&(w.ds.min(0)>=2))
    for split,count in [('train',300),('val',60)]:
        buckets=collections.defaultdict(list)
        for i in ids:
            block=tuple(np.floor(xz(w.grid[i])/2).astype(int))
            if region(block)==split:buckets[block].append(int(i))
        for b in buckets:rng.shuffle(buckets[b])
        blocks=list(buckets);rng.shuffle(blocks)
        picked=0
        while picked<count:
            for b in blocks:
                if not buckets[b]:continue
                i=buckets[b].pop();cases.append(dict(id=f'C-{split}-{picked:03}',i=i,k='C',yaw=float(rng.uniform(-math.pi,math.pi)),split=split,block='/'.join(map(str,b)),mode='teacher'));picked+=1
                if picked==count:break
            if not any(buckets.values()) and picked<count:raise RuntimeError('Not enough distinct starts')
    vc=[c for c in cases if c['split']=='val']
    c=max(vc,key=lambda c:w.ds[:,c['i']].min())
    for mode in ['early_stop','look_away']:cases.append(dict(c,id='X-C-'+mode,split='control',mode=mode,paired=c['id']))
    return cases
def measures(w,p):
    return {k:min((d for q in rr if (d:=geo(w.pf,p,q)) is not None),default=None) for k,rr in w.refs.items()}
def rollout(w,c):
    path,r=w.route(c['k'],c['i']);start=path[0];k=c['k'];mode=c['mode'];w.reset(start,c['yaw'])
    ep=ROOT/'episodes'/c['id'];ep.mkdir(exist_ok=True,parents=True)
    rows=[];sheet=None;dist=0.;hits=0;idx=1;startgeo=measures(w,start);planstop=False;reason=None
    def obs(t):
        nonlocal sheet
        j=t%64
        if j==0:sheet=Image.new('RGB',(W*8,H*8))
        frame=w.rgb();sheet.paste(Image.fromarray(frame),((j%8)*W,(j//8)*H))
        return frame
    def flush(t):
        used=t%64+1;sheet.crop((0,0,W*8,math.ceil(used/8)*H)).save(ep/f'rgb-{t//64:02}.jpg',quality=86,subsampling=1)
    t=0
    while True:
        pos,yaw=w.pose();frame=obs(t)
        if reason: # Collision/time cutoff: final observation does not create a STOP label.
            rows.append(dict(t=t,xyz=pos.tolist(),yaw=yaw,action=None,collision=False));flush(t);break
        v=0.;omega=0.;stop=False
        while idx<len(path) and hd(pos,path[idx])<.0025:idx+=1
        if mode=='early_stop' and dist>=1.:stop=True
        elif idx<len(path):
            target=path[idx];dy=wrap(heading(pos,target)-yaw)
            if abs(dy)>.003:omega=float(np.clip(dy/DT,-1,1))
            else:v=min(.4,hd(pos,target)/DT)
        else:
            dy=wrap(heading(pos,w.anchor[k])+(math.pi if mode=='look_away' else 0)-yaw)
            if abs(dy)>.004:omega=float(np.clip(dy/DT,-1,1))
            else:stop=True
        coll=False
        if stop:planstop=True;reason='stop'
        else:
            a='move_forward' if v else ('turn_left' if omega>0 else 'turn_right')
            w.agent.agent_config.action_space[a].actuation.amount=float(v*DT if v else math.degrees(abs(omega)*DT))
            reported=w.agent.act(a);nxt,_=w.pose()
            coll=bool(reported or (v and hd(pos,nxt)+.0015<v*DT))
            hits+=int(coll);dist+=float(np.linalg.norm(nxt-pos))
            if hits>=3:reason='collision_limit'
            elif t+1>=600:reason='timeout'
        rows.append(dict(t=t,xyz=pos.tolist(),yaw=yaw,action=[v,omega,int(stop)],collision=coll))
        if stop or t%64==63:flush(t)
        if stop:break
        t+=1
    terminal=w.visible();finalgeo=measures(w,pos)
    near=[j for j,d in finalgeo.items() if d is not None and d<=.8];seen=[j for j,hit in terminal.items() if hit['visible']]
    common=sorted(set(near)&set(seen));passed=bool(planstop and common and hits<3)
    reason=reason if not planstop else ('success' if passed else 'stopped_too_far' if not near else 'goal_out_of_view' if not common else 'failed')
    short=min(d for d in startgeo.values() if d is not None)
    summary=dict(id=c['id'],scene=w.name,split=c['split'],start_block=c['block'],mode=mode,paired=c.get('paired'),goal_text='소화기',goal_class='fire extinguisher',teacher_instance=k,
       approach_view=f'{k}-{r}',start_xyz=start.tolist(),start_yaw=c['yaw'],end_xyz=pos.tolist(),start_geo_m=short,final_geo_m=finalgeo,travel_m=dist,
       step_observations=len(rows),commands=sum(row['action'] is not None for row in rows),duration_s=(len(rows)-1)*DT,collisions=hits,explicit_stop=planstop,
       near_ids=near,visible_ids=seen,matching_ids=common,visibility=terminal,success_auto=passed,reason=reason,spl_auto=float(short/max(short,dist,1e-9)) if passed else 0.,
       human_review='pending',use_for_imitation=bool(c['split']=='train' and mode=='teacher' and passed))
    Image.fromarray(frame).save(ep/'last.png')
    (ep/'actions.jsonl').write_text(''.join(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n' for row in rows))
    dump(ep/'episode.json',summary);return summary
def main():
    p=argparse.ArgumentParser();p.add_argument('--scene',choices=['fire','castle','all'],default='all');p.add_argument('--pilot',action='store_true');p.add_argument('--resume',action='store_true');a=p.parse_args()
    for name in (['fire','castle'] if a.scene=='all' else [a.scene]):
        w=World(name)
        try:
            cases=tasks(w)
            if a.pilot:cases=cases[:3]+cases[-2:]
            for i,c in enumerate(cases):
                if a.resume and (ROOT/'episodes'/c['id']/'episode.json').exists():continue
                s=rollout(w,c)
                if a.pilot or i%10==0 or i==len(cases)-1:print(i,s['id'],s['reason'],s['commands'],round(s['travel_m'],2),flush=True)
        finally:w.close()
if __name__=='__main__':main()
