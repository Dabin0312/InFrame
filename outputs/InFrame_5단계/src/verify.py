"""Re-run logged control inputs through Habitat and independently score their terminal RGB and range."""
import hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image
from evaluate import ROOT, PRIOR, World, geo, DT, move

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def check(world,case,h):
    folder=ROOT/'episodes'/f'h{h}'/case['id']
    rows=[json.loads(line) for line in (folder/'steps.jsonl').read_text().splitlines()]
    r=json.loads((folder/'result.json').read_text())
    world.reset(np.asarray(case['start_xyz']),case['start_yaw'])
    assert r['initial_rgb_sha256']==hashlib.sha256(world.rgb().tobytes()).hexdigest()
    assert len(rows)==r['observations'] and r['goal']==case['goal_text']
    count=0;length=0.;stopped=False
    for i,row in enumerate(rows):
        p,yaw=world.pose()
        assert row['t']==i and np.allclose(p,row['xyz'],rtol=0,atol=1e-4)
        assert abs((yaw-row['yaw']+np.pi)%(2*np.pi)-np.pi)<1e-4
        cmd=row['action']
        if cmd is None:
            assert i==len(rows)-1 and (count==3 or i==600);break
        v,omega,stop=cmd
        assert 0<=v<=.400001 and abs(omega)<=1.000001 and stop in (0,1)
        if stop:
            assert i==len(rows)-1 and v==0 and omega==0 and i<600
            stopped=True;break
        assert count<3 and i<600
        collision,delta=move(world,cmd)
        assert collision==row['collision']
        length+=delta;count+=int(collision)
    assert r['collisions']==count and abs(length-r['travel_m'])<.002
    assert stopped==r['stop'] and r['elapsed_s']==(len(rows)-1)*DT
    frame=world.rgb();last=np.asarray(Image.open(folder/'last.png'))
    assert np.abs(frame.astype(float)-last).mean()<1
    n=len(rows);j=(n-1)%64
    sheets=list(folder.glob('rgb-*.jpg'));assert len(sheets)==(n+63)//64
    for i,sheet in enumerate(sorted(sheets)):
        with Image.open(sheet) as img:
            img.verify()
    with Image.open(folder/f'rgb-{(n-1)//64:02}.jpg') as img:
        x=(j%8)*192;y=(j//8)*144
        cropped=np.asarray(img.crop((x,y,x+192,y+144)))
        assert np.abs(cropped.astype(float)-last).mean()<13
    seen={k for k,v in world.visible().items() if v['visible']}
    ds={k:min(geo(world.pf,p,q) for q in rr) for k,rr in world.refs.items()}
    near={k for k,d in ds.items() if d<=.8}
    passed=bool(stopped and count<3 and (near&seen))
    assert passed==r['success'] and sorted(seen)==r['visible_ids'] and sorted(near)==r['near_ids']
    expected='success' if passed else ('stopped_too_far' if not near else 'goal_out_of_view') if stopped else 'collision_limit' if count==3 else 'timeout'
    assert expected==r['reason']
    shortest=min(geo(world.pf,np.array(case['start_xyz']),q) for rr in world.refs.values() for q in rr)
    assert abs(shortest-r['start_geo_m'])<.001 and abs(r['spl']-(shortest/max(shortest,length) if passed else 0))<.001
    return r

def main():
    prior=json.loads((PRIOR/'manifest.json').read_text());train=json.loads((ROOT/'training_data.json').read_text())
    assert set(train['train_ids'])=={r['id'] for r in prior if r['use_for_imitation']} and len(train['train_ids'])==297
    starts=[r for r in prior if r['split']=='val'];assert len(starts)==60
    blocks={e['start_block'] for e in prior if e['id'] in train['train_ids']}
    assert not blocks.intersection({r['start_block'] for r in starts})
    w=World('castle',register=False);pairs=[]
    try:
        for case in starts:
            a,b=[check(w,case,h) for h in (1,4)]
            assert a['initial_rgb_sha256']==b['initial_rgb_sha256'] and a['initially_visible']==b['initially_visible']
            pairs.append([a,b])
    finally:w.close()
    summary={}
    for j,h in enumerate([1,4]):
        runs=[p[j] for p in pairs];N=len(runs);success=sum(r['success'] for r in runs)
        summary[str(h)]=dict(n=N,success=success,rate=success/N,mean_spl=float(np.mean([r['spl'] for r in runs])),
                            reason=dict(Counter(r['reason'] for r in runs)),initially_unseen=sum(not r['initially_visible'] for r in runs),
                            success_from_unseen=sum(r['success'] and not r['initially_visible'] for r in runs),observations=sum(r['observations'] for r in runs))
    votes=Counter(('both' if a['success'] and b['success'] else 'one_only' if a['success'] else 'four_only' if b['success'] else 'neither') for a,b in pairs)
    report=dict(training_episodes=297,training_frames=train['images'],evaluation_scene='Skokloster Castle',goal='소화기',models=summary,
                paired={k:votes[k] for k in ['both','one_only','four_only','neither']},
                same_initial_rgb_pairs=60,train_val_start_block_overlap=0,replayed_and_rescored=120,blind_human_review='pending',
                frozen_checkpoint_sha256={str(h):sha(ROOT/'checkpoints'/f'student-{h}.pt') for h in (1,4)})
    (ROOT/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    (ROOT/'paired_runs.json').write_text(json.dumps(pairs,ensure_ascii=False))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
