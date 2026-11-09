"""Independently replay the success predicate, per-step action/pose and recorded image checks."""
from world import *
from teacher import region
from dataset import rgb
from PIL import Image
from collections import Counter
import hashlib
def main():
    rows=sorted([json.loads(p.read_text()) for p in (ROOT/'episodes').glob('*/episode.json')],key=lambda q:q['id']);worlds={};counts=Counter();md={}
    splits={};starts=set();steps_n=0;maperr=0.;rgbmae=0.;samples=0;seen_start=set()
    try:
        for s in sorted(rows,key=lambda e:(e['scene'],e['id'])):
            name=s['scene'];ep=ROOT/'episodes'/s['id']
            if name not in worlds:
                for prior in worlds.values():prior.close()
                worlds.clear();worlds[name]=World(name,register=False)
            w=worlds[name];pf=w.pf
            tr=[json.loads(l) for l in (ep/'actions.jsonl').read_text().splitlines()];n=len(tr)
            assert len(tr)==s['step_observations'] and len({v['t'] for v in tr})==n
            steps_n+=n;poses=np.array([r['xyz'] for r in tr]);assert np.allclose(poses[0],s['start_xyz']) and np.allclose(poses[-1],s['end_xyz'])
            hits=0;stops=0
            for i,r in enumerate(tr):
                assert r['t']==i
                assert pf.get_island(poses[i])==w.island
                assert hd(pf.snap_point(poses[i],w.island),poses[i])<.002
                if r['action'] is None:assert i==n-1 and not s['explicit_stop'];continue
                v,om,stop=r['action'];assert 0<=v<=.4+1e-6 and abs(om)<=1.00001 and stop in (0,1)
                hits+=int(r['collision']);stops+=stop
                if stop:assert i==n-1 and not v and not om;continue
                assert i+1<n
                dp=hd(poses[i],poses[i+1])
                assert dp<=v*DT+.003 and abs(wrap(tr[i+1]['yaw']-r['yaw']-om*DT))<.0015
                if not r['collision']:assert abs(dp-v*DT)<.002
            assert hits==s['collisions'] and stops==int(s['explicit_stop']) and n-1<=600
            assert n-int(tr[-1]['action'] is None)==s['commands']
            if s['reason']=='collision_limit':assert hits==3 and not stops
            if s['reason']=='timeout':assert n-1==600 and not stops
            # Decode and validate every sheet, its frame count, and raw terminal PNG vs saved tile.
            sheets=sorted(ep.glob('rgb-*.jpg'));assert len(sheets)==math.ceil(n/64)
            for j,p in enumerate(sheets):
                with Image.open(p) as im:
                    im.load();assert im.size==(8*W,H*math.ceil(min(64,n-64*j)/8))
            last=np.array(Image.open(ep/'last.png').convert('RGB'))
            mae=float(np.mean(np.abs(np.array(rgb(ep,n-1),dtype=float)-last)));assert mae<12
            rgbmae=max(rgbmae,mae)
            # Independent end-pose render from disk; use numeric yaw and registered points, no terminal flags as inputs.
            w.reset(poses[-1],tr[-1]['yaw']);vis=w.visible()
            err=float(np.mean(np.abs(w.rgb().astype(float)-last)));assert err<2,(s['id'],err);maperr=max(maperr,err)
            near=[];seen=[]
            for k,rr in w.refs.items():
                d=min(geo(pf,poses[-1],p) for p in rr)
                assert abs(d-s['final_geo_m'][k])<.001
                if d<=.8:near.append(k)
                if vis[k]['visible']:seen.append(k)
            ok=bool(stops and hits<3 and set(near)&set(seen));assert sorted(near)==sorted(s['near_ids']) and sorted(seen)==sorted(s['visible_ids']) and ok==s['success_auto']
            assert abs(np.linalg.norm(np.diff(poses,axis=0),axis=1).sum()-s['travel_m'])<.001
            assert abs(min(geo(pf,poses[0],p) for rr in w.refs.values() for p in rr)-s['start_geo_m'])<.001
            assert s['use_for_imitation']==bool(s['split']=='train' and ok and s['mode']=='teacher')
            if s['split'] in ('train','val'):
                b=tuple(np.floor(xz(poses[0])/2).astype(int));assert region(b)==s['split'];splits.setdefault(s['split'],set()).add(b);t=tuple(poses[0].round(4));assert t not in starts;starts.add(t)
            counts[s['split']]+=1
            if s['paired']:
                pair=next(q for q in rows if q['id']==s['paired']);assert np.allclose(pair['start_xyz'],s['start_xyz']) and abs(pair['start_yaw']-s['start_yaw'])<1e-6 and pair['success_auto'] and not ok
        assert counts=={'train':300,'val':60,'control':4,'near':22} and not (splits['train']&splits['val'])
        dump(ROOT/'manifest.json',rows)
        group={}
        for k in counts:
            subset=[s for s in rows if s['split']==k];group[k]=dict(total=len(subset),success_auto=sum(s['success_auto'] for s in subset),reasons=dict(Counter(s['reason'] for s in subset)),
             min_start_geodesic_m=min(s['start_geo_m'] for s in subset),max_start_geodesic_m=max(s['start_geo_m'] for s in subset),mean_spl_auto=np.mean([s['spl_auto'] for s in subset]))
        report=dict(episodes=len(rows),observations=steps_n,commands=sum(s['commands'] for s in rows),unique_wide_starts=len(starts),train_val_start_block_overlap=0,block_size_m=2.,
         train_blocks=len(splits['train']),val_blocks=len(splits['val']),bounds_checked_for_all_commands=True,all_endposes_rerendered=True,all_steps_on_expected_floor=True,
         max_rerender_rgb_mae_255=maperr,max_jpeg_terminal_mae_255=rgbmae,human_blind_ratings_pending=True,groups=group)
        dump(ROOT/'verification.json',report);print(json.dumps(report,indent=2))
    finally:
        for w in worlds.values():w.close()
if __name__=='__main__':main()
