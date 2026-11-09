"""Score matched starts, independently replay simulator actions, and audit split provenance."""
from collections import Counter
import math
import json
import numpy as np
from scipy.spatial import cKDTree
from PIL import Image
from common import ROOT,S4,S5,WORK,read,write,sha,block
from evaluate import World,move,distances,hd
from teacher import region

def read_steps(path):
    return [json.loads(v) for v in path.read_text().splitlines()]

def failure_kind(r,steps):
    if r['reason']=='collision_limit':return 'boundary'
    if r['reason']!='timeout':return r['reason']
    recent=steps[-81:-1]
    actions=[row['action'] for row in recent]
    flips=sum(a[1]*b[1]<0 for a,b in zip(actions,actions[1:]))
    if max(hd(row['xyz'],steps[-1]['xyz']) for row in recent)<.12 and flips>=12:return 'rotation'
    return 'other_timeout'

def validate(w,r,steps,folder):
    import hashlib
    w.reset(np.asarray(r['start_xyz']),r['start_yaw'])
    start=w.rgb()
    if hashlib.sha256(start.tobytes()).hexdigest()!=r['initial_rgb_sha256']:
        # RGB sheets store aligned 192x144 JPEG tiles. Compare a fresh encoding.
        from io import BytesIO
        buf=BytesIO();Image.fromarray(start).save(buf,format='JPEG',quality=83,subsampling=1);buf.seek(0)
        rendered=np.asarray(Image.open(buf)).astype(float)
        assert np.abs(rendered-first_tile(folder)).mean()<.1
    hits=0;length=0.
    for i,row in enumerate(steps):
        p,yaw=w.pose()
        assert i==row['t'] and np.linalg.norm(p-row['xyz'])<1e-4
        assert abs((yaw-row['yaw']+np.pi)%(2*np.pi)-np.pi)<1e-4
        cmd=row['action']
        if cmd is None:
            assert i==len(steps)-1 and (i==600 or hits==3);break
        v,om,stop=cmd
        assert 0<=v<=.40001 and abs(om)<=1.00001
        if stop:
            assert i==len(steps)-1 and v==om==0 and hits<3 and i<600;break
        assert hits<3 and i<600
        collision,d=move(w,cmd)
        assert collision==row['collision']
        hits+=int(collision);length+=d
    assert hits==r['collisions'] and abs(length-r['travel_m'])<.002
    assert np.abs(w.rgb().astype(float)-np.asarray(Image.open(folder/'last.png'))).mean()<1
    final=distances(w,w.pose()[0])['C'];seen=w.visible()['C']['visible']
    stopped=bool(steps[-1]['action'] is not None and steps[-1]['action'][2])
    success=bool(stopped and hits<3 and final<=.8 and seen)
    assert stopped==r['stop'] and success==r['success'] and abs(final-r['final_geo_m']['C'])<.002
    assert bool(r['visible_ids'])==seen
    shortest=distances(w,np.asarray(r['start_xyz']))['C']
    assert abs(r['spl']-(shortest/max(shortest,length) if success else 0.))<.002

def first_tile(folder):
    with Image.open(folder/'rgb-00.jpg') as frame:
        return np.asarray(frame.crop((0,0,192,144))).astype(float)

def summarize_pair(folder,check=False,after_folder=None):
    w=World('castle',register=False) if check else None
    try:
        locations={'before':folder,'after':after_folder or folder}
        conditions={mode:read(locations[mode]/(mode+'.json')) for mode in locations}
        assert [r['start_id'] for r in conditions['before']]==[r['start_id'] for r in conditions['after']]
        stats={};pairs=[]
        for a,b in zip(conditions['before'],conditions['after']):
            assert a['start_xyz']==b['start_xyz'] and a['start_yaw']==b['start_yaw']
            if a['initial_rgb_sha256']!=b['initial_rgb_sha256']:
                assert np.array_equal(first_tile(locations['before']/'before'/a['start_id']),
                                      first_tile(locations['after']/'after'/b['start_id']))
            pair=[]
            for mode,r in [('before',a),('after',b)]:
                ep=locations[mode]/mode/r['start_id'];steps=read_steps(ep/'steps.jsonl')
                assert r==read(ep/'result.json')
                if check:validate(w,r,steps,ep)
                pair.append(dict(r,variant=mode,kind=failure_kind(r,steps)))
            pairs.append(pair)
        for j,mode in enumerate(['before','after']):
            runs=[p[j] for p in pairs]
            stats[mode]=dict(total=len(runs),success=sum(r['success'] for r in runs),
               rate=float(np.mean([r['success'] for r in runs])),mean_spl=float(np.mean([r['spl'] for r in runs])),
               outcomes=dict(Counter(r['kind'] for r in runs)),impacts=sum(r['collisions'] for r in runs),
               runs_with_contact=sum(bool(r['collisions']) for r in runs),
               initially_invisible=sum(not r['initially_visible'] for r in runs),success_from_invisible=sum(r['success'] and not r['initially_visible'] for r in runs))
        recover=sum(not a['success'] and b['success'] for a,b in pairs)
        regress=sum(a['success'] and not b['success'] for a,b in pairs)
        paired=dict(recovered=recover,regressed=regress,both_success=sum(a['success'] and b['success'] for a,b in pairs),
                    both_failed=sum(not a['success'] and not b['success'] for a,b in pairs))
        return dict(policies=stats,paired=paired,transitions=dict(Counter(a['kind']+' → '+b['kind'] for a,b in pairs))),pairs
    finally:
        if w:w.close()

def main():
    info=read(ROOT/'봉인_출발점.json');spec=read(ROOT/'학습구역.json')
    assert sha(ROOT/'봉인_출발점.json')==spec['holdout_sha256']
    assert all(region(tuple(p['block']))=='reserved' for p in info['cases'])
    assert len(info['cases'])==len(set(tuple(x['start_xyz']) for x in info['cases']))==60
    corr=read(ROOT/'교정자료.json')
    devset={tuple(b) for b in spec['dev_blocks']}
    assert all(region(tuple(x['block']))=='train' and tuple(x['block']) not in devset for x in corr['positions'])
    for mode in ['train_cases','dev_cases']:
        assert all(region(tuple(x['block']))=='train' for x in spec[mode])
    dock=read(ROOT/'정지자료.json')['centers']
    assert all(region(block(p))=='train' and block(p) not in devset for p in dock)
    centers=[[x['x'],x['z']] for x in corr['positions']]+[[p[0],p[2]] for p in dock]
    tree=cKDTree(centers)
    from freeze import artifacts
    lock=read(ROOT/'모델봉인.json')
    assert all(sha(path)==lock[key] for key,path in artifacts().items())
    min_correction=float(min(tree.query(np.asarray(r['start_xyz'])[[0,2]])[0] for r in info['cases']))
    fresh_xz=np.array([c['start_xyz'] for c in info['cases']])[:,[0,2]]
    additional_trajectories={}
    for folder in [WORK/'train/before',WORK/'dev/before',WORK/'dev/after',WORK/lock['development_run']/'after']:
        xs=[row['xyz'] for path in folder.glob('*/steps.jsonl') for row in read_steps(path)]
        if xs:
            nearest=cKDTree(np.asarray(xs)[:,[0,2]]).query(fresh_xz)[0]
            assert min(nearest)>.001
            additional_trajectories[str(folder.relative_to(WORK))]=float(min(nearest))
    fresh,pairs=summarize_pair(ROOT/'episodes',True)
    assert [p[0]['start_id'] for p in pairs]==[c['id'] for c in info['cases']]
    for (a,b),c in zip(pairs,info['cases']):
        assert np.allclose(a['start_xyz'],c['start_xyz']) and a['start_yaw']==c['start_yaw']
    train,repairs=summarize_pair(WORK/'train')
    dev,dp=summarize_pair(WORK/'dev',after_folder=WORK/read(ROOT/'모델봉인.json')['development_run'])
    write(ROOT/'개발_쌍별.json',dp)
    write(ROOT/'평가결과.json',dict(fresh=fresh,development=dev,training_area=train,
        registered_starts_sha256=sha(ROOT/'봉인_출발점.json'),model_lock=read(ROOT/'모델봉인.json'),
        min_test_start_to_correction_m=min_correction,min_test_start_to_additional_traces_m=additional_trajectories,episodes_replayed=120,initial_pose_matched_pairs=60,
        initial_rgb_hash_matched_pairs=sum(a['initial_rgb_sha256']==b['initial_rgb_sha256'] for a,b in pairs),
        initial_rgb_raw_mismatch=[a['start_id'] for a,b in pairs if a['initial_rgb_sha256']!=b['initial_rgb_sha256']],
        initial_archived_rgb_matched_pairs=sum(np.array_equal(first_tile(ROOT/'episodes/before'/a['start_id']),first_tile(ROOT/'episodes/after'/a['start_id'])) for a,b in pairs),human_rating='pending'))
    write(ROOT/'시험_쌍별.json',pairs)
    write(WORK/'train_pairs.json',repairs)
    print('fresh',fresh,flush=True)
if __name__=='__main__':main()
