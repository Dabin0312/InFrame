"""Closed-loop evaluation of frozen students. Each policy action advances the robot."""
import argparse, contextlib, hashlib, json, math, struct, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT.parent/'InFrame_4단계'
sys.path.insert(0,str(PRIOR/'src'))
from world import World, geo, hd, DT, W, H

class RemotePolicy:
    def __init__(self,python,checkpoint):
        self.process=subprocess.Popen([str(python),str(ROOT/'src/inference_worker.py'),str(checkpoint)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def reset(self,goal):
        self.process.stdin.write(b'R'+goal.encode('utf-8')+b'\n')
    def act(self,frame):
        self.process.stdin.write(b'F'+frame.tobytes());self.process.stdin.flush()
        packet=self.process.stdout.read(9)
        if len(packet)!=9:raise RuntimeError('Policy process failed')
        return struct.unpack('<ffB',packet)
    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        if self.process.wait()!=0:raise RuntimeError('Policy process exited unsuccessfully')

class Frames:
    def __init__(self,folder):
        self.folder=folder;self.sheet=None
    def add(self,index,frame,last):
        j=index%64
        if j==0:self.sheet=Image.new('RGB',(8*W,8*H))
        self.sheet.paste(Image.fromarray(frame),((j%8)*W,(j//8)*H))
        if j==63 or last:
            self.sheet.crop((0,0,8*W,math.ceil((j+1)/8)*H)).save(self.folder/f'rgb-{index//64:02}.jpg',quality=83,subsampling=1)

def move(world,action):
    v,omega,_=action
    before,_=world.pose()
    # The bounded twist is integrated over one 0.25 s command using midpoint heading.
    engine_hit=False
    turn='turn_left' if omega>0 else 'turn_right'
    def rotate(fraction):
        world.agent.agent_config.action_space[turn].actuation.amount=math.degrees(abs(omega)*DT*fraction)
        return world.agent.act(turn)
    if omega:engine_hit=bool(rotate(.5 if v else 1.))
    if v:
        world.agent.agent_config.action_space['move_forward'].actuation.amount=v*DT
        engine_hit=world.agent.act('move_forward') or engine_hit
        if omega:engine_hit=rotate(.5) or engine_hit
    after,_=world.pose()
    return bool(engine_hit or (v>0 and hd(before,after)+.0015<v*DT)),float(np.linalg.norm(after-before))

def distances(world,position):
    return {k:min(geo(world.pf,position,q) for q in points) for k,points in world.refs.items()}

def trial(world,policy,case,history,folder):
    folder.mkdir(parents=True,exist_ok=True)
    archive=Frames(folder);collision_count=0;length=0.;reason=None;rows=[]
    world.reset(np.asarray(case['start_xyz']),case['start_yaw']);policy.reset(case['goal_text'])
    start,_=world.pose();initial_rgb=world.rgb();start_hash=hashlib.sha256(initial_rgb.tobytes()).hexdigest()
    initial_distance=min(distances(world,start).values())
    initially_visible=bool(world.visible()['C']['visible'])
    for i in range(601):
        pos,yaw=world.pose();rgb=initial_rgb if i==0 else world.rgb()
        command=None;collision=False
        if reason is None:
            command=policy.act(rgb)
            if command[2]:
                reason='stop'
            else:
                collision,moved=move(world,command);length+=moved;collision_count+=int(collision)
        terminal=reason is not None
        archive.add(i,rgb,terminal)
        rows.append(dict(t=i,xyz=pos.tolist(),yaw=yaw,action=command,collision=collision))
        if terminal:break
        if collision_count>=3:reason='collision_limit'
        elif i+1>=600:reason='timeout'
    if not terminal:raise RuntimeError('Missing terminal observation')
    visible=world.visible();distance=distances(world,pos)
    stopped=reason=='stop'
    close={k for k,d in distance.items() if d<=.8};seen={k for k,hit in visible.items() if hit['visible']}
    success=bool(stopped and close&seen)
    if stopped:reason='success' if success else 'stopped_too_far' if not close else 'goal_out_of_view'
    result=dict(start_id=case['id'],history=history,goal=case['goal_text'],scene=case['scene'],initial_rgb_sha256=start_hash,initially_visible=initially_visible,
        start_xyz=start.tolist(),start_yaw=case['start_yaw'],end_xyz=pos.tolist(),start_geo_m=initial_distance,final_geo_m=distance,travel_m=length,
        observations=len(rows),commands=sum(r['action'] is not None for r in rows),elapsed_s=i*DT,collisions=collision_count,stop=stopped,visible_ids=sorted(seen),
        near_ids=sorted(close),visibility=visible,success=success,reason=reason,spl=initial_distance/max(initial_distance,length) if success else 0.)
    Image.fromarray(rgb).save(folder/'last.png')
    (folder/'steps.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in rows))
    (folder/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
    return result

def main(args):
    manifest=json.loads((PRIOR/'manifest.json').read_text())
    if args.smoke:
        starts=[s for s in manifest if s['use_for_imitation']][::55]
    else:
        starts=[s for s in manifest if s['split']=='val']
        assert len(starts)==60 and len({s['start_block'] for s in starts})==10
    w=World('castle',register=False)
    try:
        for h in args.history:
            ckpt=ROOT/'checkpoints'/f'student-{h}.pt'
            with contextlib.closing(RemotePolicy(args.torch_python,ckpt)) as policy:
                for j,case in enumerate(starts):
                    ep=args.out/f'h{h}'/case['id']
                    result=trial(w,policy,case,h,ep)
                    print(h,j,case['id'],result['reason'],round(result['final_geo_m']['C'],2),result['commands'],flush=True)
    finally:w.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--torch-python',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'episodes')
    p.add_argument('--smoke',action='store_true');p.add_argument('--history',nargs='+',type=int,choices=(1,4),default=[1,4]);main(p.parse_args())
