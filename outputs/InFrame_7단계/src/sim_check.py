"""New closed-loop Habitat rollouts through the Go2 camera and motor interfaces."""
import argparse
from collections import Counter
from contextlib import closing
import csv
import gzip
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from PIL import Image
from bridge import Decision, MotionGuard, MockSport, PERIOD
from devices import FROZEN, ROOT, FrontCamera, MockVideo, verify_policy

S5 = ROOT.parent/'InFrame_5단계'
S6 = ROOT.parent/'InFrame_6단계_정책개선'
sys.path.insert(0,str(S5/'src'))
from evaluate import World, move, distances


def read(path):
    return json.loads(path.read_text())


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


class PolicyPipe:
    def __init__(self, python):
        self.p = subprocess.Popen([python,str(FROZEN/'worker.py'),str(FROZEN/'recovery.pt')],
                                  stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def reset(self):
        self.p.stdin.write('R소화기\n'.encode())
    def act(self,rgb):
        self.p.stdin.write(b'F'+rgb.tobytes())
        self.p.stdin.flush()
        packet = self.p.stdout.read(9)
        if len(packet)!=9:
            raise IOError('Frozen policy worker exited')
        return struct.unpack('<ffB',packet)
    def close(self):
        self.p.stdin.close()
        if self.p.wait(timeout=15):
            raise RuntimeError('Policy worker failed')


def rollout(world,policy,case,out,mode='normal',forward=.4,yaw=1.):
    key=case['id']
    world.reset(np.asarray(case['start_xyz']),case['start_yaw'])
    policy.reset()
    t=0.
    clock=lambda: t
    camera=FrontCamera(MockVideo(world.rgb),clock)
    sport=MockSport()
    events=[]
    guard=MotionGuard(sport,clock,emit=events.append,forward=forward,yaw=yaw)
    guard.start()
    rows=[]
    shots=[]
    distance=0.
    impacts=0
    lost_at=None
    end_position=None
    save_frames = (key=='FRESH-015' and mode in ('normal','cut'))
    # Keep integrating the last twist even when the camera stops producing frames.
    for step in range(610):
        t=step*PERIOD
        pos,heading=world.pose()
        if impacts>=3 and not guard.reason:
            guard.stop('collision_limit')
        guard.tick()
        request=None
        frame_ok=False
        if not guard.reason and lost_at is None:
            stamp,rgb=camera.read()
            request=policy.act(rgb)
            guard.accept(Decision(step,stamp,request))
            frame_ok=True
            if save_frames:
                shots.append(rgb.copy())
            if mode=='cut' and distance>=1. and sport.twist[0]>.20:
                lost_at=t
        vx,vy,w=sport.twist
        assert 0<=vx<=forward and vy==0 and abs(w)<=yaw
        row=dict(t=t,xyz=pos.tolist(),yaw=heading,raw=request,sent=[vx,vy,w],frame=frame_ok,
                 state=guard.reason,travel_m=distance,total_hits=impacts)
        rows.append(row)
        if guard.reason:
            assert guard.stop_confirmed and sport.twist==(0.,0.,0.)
            if mode!='cut':
                break
            if end_position is None:
                end_position=pos.copy()
            assert np.array_equal(pos,end_position)
            if t>=lost_at+1.5:
                break
        collision,delta=move(world,(vx,w,False))
        row['hit']=collision
        distance+=delta
        impacts+=int(collision)
    else:
        raise AssertionError('Episode did not terminate')
    final=world.pose()[0]
    goal_distance=distances(world,final)['C']
    visible=bool(world.visible()['C']['visible'])
    success=guard.reason=='goal_stop' and goal_distance<=.8 and visible
    last=world.rgb()
    (out/'last'/mode).mkdir(parents=True,exist_ok=True)
    Image.fromarray(last).save(out/'last'/mode/(key+'.png'))
    if save_frames:
        media=out/'media'
        media.mkdir(exist_ok=True)
        # Frames after dropout are verifier-camera renders, never fed to the policy.
        if mode=='cut':
            for r in rows[len(shots):]:
                world.reset(np.array(r['xyz']),r['yaw'])
                shots.append(world.rgb().copy())
        np.savez_compressed(media/(key+('-rgb' if mode=='normal' else '-cut-monitor')+'.npz'),
                            rgb=np.stack(shots))
    logdir=out/'traces'/mode
    logdir.mkdir(parents=True,exist_ok=True)
    with gzip.open(logdir/(key+'.json.gz'),'wt',encoding='utf-8') as trace:
        json.dump(dict(steps=rows,commands=events),trace,separators=(',',':'),allow_nan=False)
    result=dict(id=key,mode=mode,success=bool(success),reason=guard.reason,seen=visible,
                goal_distance_m=goal_distance,travel_m=distance,collisions=impacts,
                final_xyz=final.tolist(),end_s=rows[-1]['t'],frames=sum(r['frame'] for r in rows),
                moves=sum(e['rpc']=='Move' for e in events),
                peak_v=max(r['sent'][0] for r in rows),peak_abs_yaw=max(abs(r['sent'][2]) for r in rows))
    if mode=='cut':
        first_stop=next(r for r in rows if r['state']=='frame_timeout')
        last_ok=next(r for r in rows if r['t']==lost_at)
        assert first_stop['t']-lost_at==.5 and last_ok['sent'][0]>.2
        result.update(last_rgb_s=lost_at,stop_s=first_stop['t'],delay_s=first_stop['t']-lost_at,
                      last_v=last_ok['sent'][0],last_w=last_ok['sent'][2],travel_during_silence_m=first_stop['travel_m']-last_ok['travel_m'],
                      after_stop_displacement_m=0.,observed_hold_s=rows[-1]['t']-first_stop['t'])
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--torch-python',default=str(ROOT.parents[1]/'work/fire-models/env/bin/python'))
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    hashes=verify_policy()
    cases=read(S6/'봉인_출발점.json')['cases']
    previous={x['start_id']:x for x in read(S6/'episodes/after.json')}
    world=World('castle',register=False)
    try:
        with closing(PolicyPipe(args.torch_python)) as student:
            results=[]
            for case in cases:
                r=rollout(world,student,case,args.out)
                old=previous[r['id']]
                r['stage6_success']=old['success']
                r['stage6_reason']=old['reason']
                r['stage6_stop']=old['stop']
                r['stage6_time_s']=old['elapsed_s']
                r['stage6_contacts']=old['collisions']
                r['end_pose_difference_m']=float(np.linalg.norm(np.array(r['final_xyz'])-old['end_xyz']))
                results.append(r)
                if len(results)%15==0:
                    print(len(results),sum(v['success'] for v in results),flush=True)
            picked=next(c for c in cases if c['id']=='FRESH-015')
            cut=rollout(world,student,picked,args.out,'cut')
            slow=rollout(world,student,picked,args.out,'limited',forward=.2,yaw=.5)
    finally:
        world.close()
    with (args.out/'starts.csv').open('w',encoding='utf-8-sig',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    report=dict(frozen_sha256=hashes,episodes=len(results),success=sum(r['success'] for r in results),
                previous_success=sum(r['stage6_success'] for r in results),
                agree_success=sum(r['success']==r['stage6_success'] for r in results),
                agree_stop=sum((r['reason']=='goal_stop')==r['stage6_stop'] for r in results),
                agree_collision_count=sum(r['collisions']==r['stage6_contacts'] for r in results),
                outcomes=dict(Counter(r['reason'] for r in results)),confirmed_policy_stops=sum(r['reason']=='goal_stop' for r in results),
                peak_v=max(r['peak_v'] for r in results),peak_abs_yaw=max(r['peak_abs_yaw'] for r in results),
                max_end_pose_difference_m=max(r['end_pose_difference_m'] for r in results),
                max_end_time_difference_s=max(abs(r['end_s']-r['stage6_time_s']) for r in results),
                moves=sum(r['moves'] for r in results),camera_cut=cut,lower_limits=slow)
    save(args.out/'report.json',report)
    print(report,flush=True)

if __name__=='__main__':
    main()
