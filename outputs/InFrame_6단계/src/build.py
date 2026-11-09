"""Audit stage 4/5 runs and assemble a portable, offline three-way comparison."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
S4 = ROOT.parent / 'InFrame_4단계'
S5 = ROOT.parent / 'InFrame_5단계'
sys.path.insert(0, str(S5 / 'src'))
from evaluate import World, move, distances, DT
from world import hd, wrap
from dataset import rgb

POLICIES = ('teacher', 'one', 'four')
NAMES = ('지도 교사', '한 프레임', '최근 4스텝')
ASSETS = ROOT / 'data'

def read(path):
    return json.loads(path.read_text())
def lines(path):
    return [json.loads(row) for row in path.read_text().splitlines()]
def compact(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def audit_students(rerun, pairs):
    manifest = read(S4/'manifest.json')
    training = set(read(S5/'training_data.json')['train_ids'])
    assert training == {r['id'] for r in manifest if r['use_for_imitation']} and len(training) == 297
    blocks = {r['start_block'] for r in manifest if r['id'] in training}
    valid = {r['id'] for r in manifest if r['split']=='val'}
    assert len(valid)==60 and valid==set(pairs)
    assert not blocks & {r['start_block'] for r in manifest if r['split']=='val'}
    expected = read(S5/'results.json')
    for h, sha in expected['frozen_checkpoint_sha256'].items():
        assert digest(S5/'checkpoints'/f'student-{h}.pt') == sha
    max_delta = 0.; exact = 0; common_exact = 0; different=[]
    for key, pair in pairs.items():
        for saved in pair:
            sub = Path(f"h{saved['history']}")/key
            old = S5/'episodes'/sub
            fresh = rerun/sub
            current = read(fresh/'result.json')
            assert saved == read(old/'result.json')
            for field in ('start_id','history','goal','start_xyz','start_yaw','initial_rgb_sha256','stop','visible_ids','near_ids','success','reason','collisions','commands'):
                assert current[field] == saved[field], (key,field)
            end_delta = float(np.linalg.norm(np.asarray(saved['end_xyz'])-current['end_xyz']))
            max_delta = max(max_delta, end_delta)
            identical = all(digest(old/file)==digest(fresh/file) for file in ('result.json','steps.jsonl','last.png'))
            exact += identical
            if not identical:different.append(dict(id=key,history=saved['history'],end_delta_m=end_delta))
            if not any(s['success'] for s in pair):common_exact += identical
    return dict(reinferred=2*len(pairs),same_outcome=2*len(pairs),same_step_count=2*len(pairs),
                max_end_delta_m=max_delta,identical_log_result_png=exact,common_failure_identical_runs=common_exact,
                small_numeric_differences=different,train_validation_start_block_overlap=0,
                checkpoint_sha256=expected['frozen_checkpoint_sha256'])

def verify_teacher(world, case, folder, rows, students):
    start=np.array(case['start_xyz']);world.reset(start,case['start_yaw'])
    first=world.rgb();sha=hashlib.sha256(first.tobytes()).hexdigest()
    assert all(np.allclose(start,s['start_xyz'],atol=1e-6) and abs(wrap(s['start_yaw']-case['start_yaw']))<1e-6 and s['initial_rgb_sha256']==sha for s in students)
    first_saved=np.asarray(rgb(folder,0),dtype=float)
    assert np.abs(first_saved-first).mean()<10
    hits=0; traveled=0.
    for i,r in enumerate(rows):
        pos,angle=world.pose()
        assert r['t']==i and np.allclose(pos,r['xyz'],atol=1e-4,rtol=0) and abs(wrap(angle-r['yaw']))<1e-4
        action=r['action']
        if action[2]:
            assert i==len(rows)-1
            break
        coll,delta=move(world,action)
        assert coll==r['collision']
        hits+=int(coll);traveled+=delta
    assert rows[-1]['action'][2] and hits==case['collisions'] and abs(case['travel_m']-traveled)<.002
    dist=distances(world,world.pose()[0])['C'];visible=world.visible()['C']['visible']
    assert case['success_auto'] and hits<3 and dist<=.8 and visible and case['explicit_stop']
    assert np.abs(world.rgb().astype(float)-np.asarray(Image.open(folder/'last.png'))).mean()<1

def brief(s,teacher=False):
    return dict(reason=s['reason'], success=s['success_auto'] if teacher else s['success'],
        stop=s['explicit_stop'] if teacher else s['stop'],elapsed=s['duration_s'] if teacher else s['elapsed_s'],
        distance=s['travel_m'],remaining=s['final_geo_m']['C'],seen='C' in s['visible_ids'],
        collisions=s['collisions'],spl=s['spl_auto'] if teacher else s['spl'])

def trace(rows):
    count=0;out=[]
    for row in rows:
        # Collision belongs to the outgoing command. Display it once the next observation arrives.
        x,_,z=row['xyz']
        out.append([round(x,6),round(z,6),round(row['yaw'],6),row['action'],count])
        count+=int(row['collision'])
    return out

def probe(world,pos,yaw):
    """A turn and up to 30 cm straight travel, using the same radius, NavMesh and motor limits."""
    def attempt(degrees):
        world.reset(pos,yaw)
        angle=math.radians(degrees)
        while abs(angle)>1e-7:
            turn=float(np.clip(angle,-DT,DT));move(world,(0.,turn/DT,0));angle-=turn
        for _ in range(6):
            hit,_=move(world,(.2,0.,0))
            if hit:break
        end,_=world.pose()
        return dict(turn_deg=degrees,reach_m=hd(pos,end),end_xz=[float(end[0]),float(end[2])],
                    remaining_m=distances(world,end)['C'])
    straight=attempt(0)
    options=[straight]+[attempt(a) for a in range(-180,180,15) if a]
    feasible=[p for p in options if p['reach_m']>=.298]
    best=min(feasible,key=lambda p:p['remaining_m']) if feasible else max(options,key=lambda p:p['reach_m'])
    return dict(straight=straight,alternative=best,headings=24)

def diagnostic(world,rows,run):
    if run['success']:return None
    actions=[r['action'] for r in rows if r['action'] is not None]
    counts=sum(a[0]>1e-6 for a in actions)
    flips=sum(a[1]*b[1]<0 for a,b in zip(actions,actions[1:]))
    hits=[]
    for i,row in enumerate(rows[:-1]):
        if not row['collision']:continue
        requested=row['action'][0]*DT
        after=rows[i+1]
        hits.append(dict(t=i+1,command_t=i,requested=requested,moved=hd(row['xyz'],after['xyz']),
                         xz=[after['xyz'][0],after['xyz'][2]]))
    if hits:
        focus=hits[0]['t'];kind='boundary' if run['reason']=='collision_limit' else 'timeout_after_contact'
    elif counts==0 and flips>12:
        focus=next(i+1 for i in range(11,len(actions)) if sum(a[1]*b[1]<0 for a,b in zip(actions[i-11:i],actions[i-10:i+1]))>=7);kind='turns'
    else:
        focus=len(rows)-1;kind='timeout'
    row=rows[focus];pos=np.array(row['xyz']);yaw=row['yaw']
    world.reset(pos,yaw)
    metrics=dict(kind=kind,t=focus,xyz=row['xyz'],yaw=yaw,forward_commands=counts,
                 reversals=flips,commands=len(actions),contacts=hits,
                 target_visible=world.visible()['C']['visible'],goal_distance=distances(world,pos)['C'],
                 boundary_m=float(world.pf.distance_to_closest_obstacle(pos)))
    metrics['probe']=probe(world,pos,yaw)
    return metrics

def pack_images(folder,out,n):
    out.mkdir(parents=True,exist_ok=True)
    sheets=sorted(folder.glob('rgb-*.jpg'))
    assert len(sheets)==math.ceil(n/64)
    for i,f in enumerate(sheets):
        assert f.name==f'rgb-{i:02}.jpg'
        with Image.open(f) as im:
            im.load();assert im.size==(192*8,144*math.ceil(min(64,n-i*64)/8))
        shutil.copyfile(f,out/f.name)
    shutil.copyfile(folder/'last.png',out/'last.png')

def floor_map():
    cal=S4/'calibration/castle';floor=np.load(cal/'floor.npz');m=read(cal/'views.json')
    verts=floor['v'][:,[0,2]]
    # Send the actual floor triangles in simulator metres, so zoomed collision boundaries stay sharp.
    return dict(vertices=verts.round(5).tolist(),triangles=floor['t'].tolist(),target=[m['objects']['C'][i] for i in (0,2)],
                views=[[v['xyz'][0],v['xyz'][2]] for v in m['views']['C']])

def build(rerun):
    ASSETS.mkdir(exist_ok=True)
    cases=sorted([r for r in read(S4/'manifest.json') if r['split']=='val'],key=lambda r:r['id'])
    pairs={p[0]['start_id']:p for p in read(S5/'paired_runs.json')}
    audit=audit_students(rerun,pairs)
    world=World('castle',register=False);catalog=[];failures=[];combos=Counter();total_frames=0
    try:
        for case in cases:
            case_id=case['id'];case_dir=ASSETS/case_id;case_dir.mkdir(exist_ok=True)
            pair=pairs[case_id];assert [s['history'] for s in pair]==[1,4] and all(s['start_id']==case_id for s in pair)
            common=not any(s['success'] for s in pair)
            data=[];runs=[];diagnoses=[]
            for j,policy in enumerate(POLICIES):
                folder=S4/'episodes'/case_id if j==0 else S5/'episodes'/f"h{pair[j-1]['history']}"/case_id
                rows=lines(folder/('actions.jsonl' if j==0 else 'steps.jsonl'))
                if j==0:verify_teacher(world,case,folder,rows,pair)
                result=brief(case,True) if j==0 else brief(pair[j-1])
                runs.append(result);data.append(trace(rows));total_frames+=len(rows)
                pack_images(folder,case_dir/policy,len(rows))
                diag=diagnostic(world,rows,result) if common and j else None
                diagnoses.append(diag)
                if diag:
                    failures.append(dict(id=case_id,policy=policy,**result,**diag))
            (case_dir/'trace.js').write_text('window.InFrameRoutes['+compact(case_id)+']='+compact(data)+';')
            group='shared' if common else 'both' if all(s['success'] for s in pair) else 'four' if pair[1]['success'] else 'one'
            item=dict(id=case_id,start=[case['start_xyz'][0],case['start_xyz'][2]],start_yaw=case['start_yaw'],
                      initial_distance=case['start_geo_m'],group=group,runs=runs,diagnoses=diagnoses)
            catalog.append(item)
            if common:combos[' / '.join(d['kind'] for d in diagnoses[1:])]+=1
    finally:world.close()
    audit.update(teacher_replayed_success=len(cases),triples_same_start=len(cases),total_observations=total_frames,
                 common_failure_pairs=sum(c['group']=='shared' for c in catalog),common_failure_modes=dict(combos))
    write(ROOT/'재현검증.json',audit);write(ROOT/'공통실패_진단.json',failures)
    with (ROOT/'공통실패_진단.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['출발점','학생','종료 사유','사건 시각 s','사건 X m','사건 Z m','종료 X m','종료 Z m','첫 충돌 시각 s','전진 명령 수','좌우 반전 수','이동 m','경계까지 m(사건)','종료 시 목표 시야','종료 시 관측점까지 m','대안 회전 각도(좌+)','대안 진행 m'])
        for d in failures:
            end=read(S5/'episodes'/('h1' if d['policy']=='one' else 'h4')/d['id']/'result.json')['end_xyz']
            writer.writerow([d['id'],d['policy'],d['reason'],d['t']*DT,d['xyz'][0],d['xyz'][2],end[0],end[2],
                d['contacts'][0]['t']*DT if d['contacts'] else '',d['forward_commands'],d['reversals'],d['distance'],d['boundary_m'],d['seen'],d['remaining'],
                d['probe']['alternative']['turn_deg'],d['probe']['alternative']['reach_m']])
    (ASSETS/'index.js').write_text('window.InFrame='+compact(dict(cases=catalog,floor=floor_map(),checks=audit))+';')
    print(compact(audit),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--rerun',type=Path,required=True,help='Fresh student inference from Stage 5 evaluate.py --out')
    build(parser.parse_args().rerun)
