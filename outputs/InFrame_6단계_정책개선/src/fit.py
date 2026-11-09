import math,time
import numpy as np
import torch
import torch.nn.functional as F
from common import ROOT,S5,WORK,read,write,sha
from recovery_policy import CorrectionNet
from policy import VisionPolicy

def main():
    if (ROOT/'모델봉인.json').exists():
        raise FileExistsError('This evaluation is sealed. Train in a separate experiment directory.')
    seed=76134;torch.manual_seed(seed);rng=np.random.default_rng(seed)
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    torch.set_num_threads(4)
    data=np.load(WORK/'corrections.npz')
    y=data['labels'];rows=read(ROOT/'교정자료.json')['positions']
    origin=data['origin'];near=np.flatnonzero(y[:,8]<.64)
    failed=np.flatnonzero(np.array([p['kind'].startswith('failure') for p in rows])[origin])
    x=torch.from_numpy(data['rgb']).to(device);labels=torch.from_numpy(y).to(device)
    base=torch.load(S5/'checkpoints/student-4.pt',weights_only=True,map_location='cpu')['state']
    v=VisionPolicy();v.load_state_dict(base)
    net=CorrectionNet().to(device);net.vision.load_state_dict(v.vision.state_dict())
    opt=torch.optim.AdamW(net.parameters(),lr=.0009,weight_decay=.001)
    logs=[];steps=3400;start=time.monotonic()
    for i in range(steps):
        ids=np.r_[rng.integers(0,len(y),64),rng.choice(near,32),rng.choice(failed,16)]
        idx=torch.from_numpy(ids).to(device)
        im=x.index_select(0,idx).float()
        im=(im*float(rng.uniform(.94,1.06))+float(rng.uniform(-3,3))).clamp(0,255)
        target=labels.index_select(0,idx)
        out=net(im);clear=out[:,3:].sigmoid()
        steering=F.smooth_l1_loss(out[:,:2].contiguous(),target[:,:2].contiguous())
        distance=F.smooth_l1_loss(out[:,2].contiguous(),target[:,2].contiguous())
        safe=(clear-target[:,3:]).square()
        risk_loss=(safe*(1+2*(target[:,3:]<.70).float())).mean()
        loss=2.2*steering+.4*distance+3.2*risk_loss
        opt.zero_grad(set_to_none=True);loss.backward()
        opt.param_groups[0]['lr']=.00095*(.08+.92*(1+math.cos(i*math.pi/steps))/2);opt.step()
        if i%400==0 or i==steps-1:
            logs.append([i,float(loss.detach().cpu()),float(risk_loss.detach().cpu())]);print(i,logs[-1][1:],flush=True)
    weight=ROOT/'weights/recovery.pt'
    torch.save(dict(base=base,correction={k:v.detach().cpu() for k,v in net.state_dict().items()},
                    config=dict(guard=.36,behind=125.,blend=.16)),weight)
    write(ROOT/'학습기록.json',dict(seed=seed,steps=steps,batch=112,device=device,seconds=time.monotonic()-start,batch_losses=logs,base_sha256=sha(S5/'checkpoints/student-4.pt')))
if __name__=='__main__':main()
