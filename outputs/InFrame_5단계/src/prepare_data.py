"""Training targets from successful demonstrations. Absolute pose and map are never read."""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
from policy import ROOT,HEIGHT,WIDTH,DT,GOALS,resize
STAGE4=ROOT.parent/'InFrame_4단계'
sys.path.insert(0,str(STAGE4/'src'))
from dataset import steps,training_episodes

def supervision(actions, offsets=None):
    actions=np.asarray(actions)
    yaw=np.r_[0,np.cumsum(actions[:-1,1]*DT)]
    forward=np.column_stack((np.sin(yaw),np.cos(yaw)))
    lengths=actions[:,0]*DT
    pos=np.vstack((np.zeros(2),np.cumsum(forward[:-1]*lengths[:-1,None],axis=0)))
    arc=np.r_[0,np.cumsum(lengths[:-1])]
    remaining=arc[-1]-arc
    stop_pose=pos[-1]
    # The teacher faces its subject at STOP. Use that bearing near the end.
    subject=stop_pose+forward[-1]*1.0
    j=np.minimum(np.searchsorted(arc,arc+1.2),len(arc)-1)
    aim=pos[j]-pos
    close=remaining<=.55
    aim[close]=subject-pos[close]
    camera_yaw=yaw if offsets is None else yaw+offsets
    direction=np.arctan2(aim[:,0],aim[:,1])-camera_yaw
    face=np.arctan2((subject-pos)[:,0],(subject-pos)[:,1])-camera_yaw
    stop=close & (np.cos(face)>=np.cos(np.deg2rad(23.)))
    assert actions[-1,2]==1
    if offsets is None:assert stop[-1]
    return np.column_stack((np.sin(direction),np.cos(direction),np.log1p(remaining),stop)).astype('f4')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('cache',type=Path);args=parser.parse_args()
    eps=training_episodes();assert len(eps)==297
    frames=[];labels=[];lengths=[];ids=[];goals=[];times=[]
    for ep in eps:
        actions=[]
        for s in steps(ep):
            frames.append(resize(s['rgb']));actions.append(s['teacher_action']);goals.append(GOALS[s['goal']]);times.append(s['t'])
        labels.append(supervision(actions));lengths.append(len(actions));ids.append(ep.name)
    args.cache.parent.mkdir(parents=True,exist_ok=True)
    np.savez(args.cache,images=np.stack(frames),labels=np.concatenate(labels),lengths=lengths,episodes=ids,goal=np.array(goals,np.int64),time=np.array(times,np.int64))
    report=dict(train_ids=ids,episode_lengths=lengths,episodes=len(ids),images=len(frames),stop_positives=int(sum(x[:,3].sum() for x in labels)),
                source_manifest_sha256=hashlib.sha256((STAGE4/'manifest.json').read_bytes()).hexdigest())
    (ROOT/'training_data.json').write_text(json.dumps(report,indent=2))
    print('prepared',len(eps),len(frames))
if __name__=='__main__':main()
