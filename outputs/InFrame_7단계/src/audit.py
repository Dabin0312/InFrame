"""Independently replay the twists that reached the SDK-shaped sink and recheck images."""
import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from devices import ROOT
sys.path.insert(0,str(ROOT.parent/'InFrame_5단계/src'))
from evaluate import World, distances, move

def load(path):
    return json.loads(path.read_text())


def main():
    p=argparse.ArgumentParser()
    p.add_argument('folder',type=Path)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    folder=args.folder
    summary=load(folder/'report.json')
    records={r['id']:r for r in csv.DictReader((folder/'starts.csv').open(encoding='utf-8-sig'))}
    cases={r['id']:r for r in load(ROOT.parent/'InFrame_6단계_정책개선/봉인_출발점.json')['cases']}
    names=['normal','limited','cut']
    total=0
    n_commands=0
    max_pose_gap=0.
    max_rgb_mae=0.
    reasons=Counter()
    world=World('castle',register=False)
    try:
        for mode in names:
            files=sorted((folder/'traces'/mode).glob('*.json.gz'))
            assert len(files)==(60 if mode=='normal' else 1)
            for path in files:
                total+=1
                key=path.name.split('.')[0]
                log=json.load(gzip.open(path,'rt'))
                rows=log['steps']
                calls=log['commands']
                assert calls[0]['rpc']=='StopMove' and calls[0]['reason']=='startup'
                assert calls[-1]['rpc']=='StopMove' and calls[-1]['ok']
                commands={}
                for e in calls[1:]:
                    assert e['ok']
                    commands[e['t']]=e
                    n_commands+=1
                position=np.array(cases[key]['start_xyz'])
                world.reset(position,cases[key]['start_yaw'])
                applied=(0.,0.,0.)
                count=0
                length=0.
                capped=0
                for i,row in enumerate(rows):
                    now=i*.25
                    pos,yaw=world.pose()
                    gap=np.linalg.norm(pos-row['xyz'])
                    max_pose_gap=max(max_pose_gap,gap)
                    assert gap<.0002 and abs((yaw-row['yaw']+np.pi)%(2*np.pi)-np.pi)<.0002
                    assert row['t']==now and row['total_hits']==count and abs(row['travel_m']-length)<.002
                    event=commands.get(now)
                    if event:
                        if event['rpc']=='Move':
                            assert row['frame'] and row['raw']==event['raw'] and not row['raw'][2]
                            v,w,_=row['raw']
                            vmax,wmax=(.2,.5) if mode=='limited' else (.4,1.)
                            applied=(np.clip(v,0,vmax),0.,np.clip(w,-wmax,wmax))
                            assert np.allclose(event['args'],applied,atol=1e-12,rtol=0)
                            capped+=int(abs(v-applied[0])>1e-5 or abs(w-applied[2])>1e-5)
                        else:
                            assert event['rpc']=='StopMove'
                            applied=(0.,0.,0.)
                    assert list(applied)==row['sent']
                    if i<len(rows)-1:
                        hit,d=move(world,(applied[0],applied[2],0))
                        assert hit==row['hit']
                        count+=int(hit)
                        length+=d
                end=rows[-1]
                v=bool(world.visible()['C']['visible'])
                d=distances(world,world.pose()[0])['C']
                success=bool(end['state']=='goal_stop' and v and d<=.8 and count<3)
                mae=np.abs(world.rgb().astype(float)-np.asarray(Image.open(folder/'last'/mode/(key+'.png')))).mean()
                max_rgb_mae=max(max_rgb_mae,float(mae))
                assert mae<1.
                if mode=='normal':
                    assert success==(records[key]['success']=='True')
                    assert count==int(records[key]['collisions'])
                    assert abs(d-float(records[key]['goal_distance_m']))<.002
                    reasons[end['state']]+=1
                elif mode=='limited':
                    assert success and capped>0
                    limited_count=capped
                else:
                    stopped=[r for r in rows if r['state']]
                    assert len(stopped)>=5 and not success
                    assert all(r['xyz']==stopped[0]['xyz'] and r['sent']==[0,0,0] for r in stopped)
                    assert stopped[0]['t']-max(r['t'] for r in rows if r['frame'])==.5
    finally:
        world.close()
    assert dict(reasons)==summary['outcomes']
    args.out.write_text(json.dumps(dict(episodes=total,post_start_commands_checked=n_commands,
        normal_outcomes=reasons,limited_commands_actually_clamped=limited_count,
        max_step_pose_diff_m=max_pose_gap,max_terminal_rgb_mae_255=max_rgb_mae),indent=2)+'\n')
    print('Replayed',total,'episodes,',n_commands,'command calls.')

if __name__=='__main__':
    main()
