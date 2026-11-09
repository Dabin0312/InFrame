"""Fit an RGB-only terminal alignment head and retain the pretrained four-frame backbone."""
import math,time
import numpy as np
import torch
import torch.nn.functional as F
from common import ROOT,WORK,read,write,sha
from recovery_policy import DockNet,CorrectionNet

def main():
    if (ROOT/'모델봉인.json').exists():
        raise FileExistsError('This evaluation is sealed. Train in a separate experiment directory.')
    seed=62179;torch.manual_seed(seed);rng=np.random.default_rng(seed);torch.set_num_threads(4)
    dev='mps' if torch.backends.mps.is_available() else 'cpu'
    d=np.load(WORK/'dock.npz');background=np.load(WORK/'corrections.npz')
    pts=read(ROOT/'교정자료.json')['positions'];ids=background['origin']
    far=np.array([np.hypot(p['x']-3.42,p['z']-14.2)>3 for p in pts])[ids]
    bg=background['rgb'][far][::3]
    x=torch.from_numpy(np.concatenate([d['rgb'],bg])).to(dev)
    y=np.vstack([d['labels'],np.zeros((len(bg),5),np.float32)]);target=torch.from_numpy(y).to(dev)
    pos=np.flatnonzero(y[:,1]>.7);near=np.flatnonzero(y[:,0]>.6)
    weights=torch.load(ROOT/'weights/recovery.pt',map_location='cpu',weights_only=True)
    net=DockNet().to(dev);aux=CorrectionNet();aux.load_state_dict(weights['correction']);net.vision.load_state_dict(aux.vision.state_dict())
    opt=torch.optim.AdamW(net.parameters(),lr=.0007,weight_decay=.001)
    for i in range(1400):
        idx=torch.as_tensor(np.r_[rng.integers(0,len(y),56),rng.choice(near,24),rng.choice(pos,16)],device=dev)
        labels=target[idx];im=x[idx].float()*float(rng.uniform(.94,1.06))
        output=net(im)
        cls=F.binary_cross_entropy_with_logits(output[:,:2].contiguous(),labels[:,:2].contiguous())
        orient=((output[:,2:]-labels[:,2:4]).square().mean(1)*labels[:,4]).mean()
        loss=cls+orient;opt.zero_grad(set_to_none=True);loss.backward()
        opt.param_groups[0]['lr']=.00065*(.08+.92*(1+math.cos(math.pi*i/1400))/2);opt.step()
    weights['dock']={k:v.cpu() for k,v in net.state_dict().items()}
    weights['config']=dict(guard=.24,behind=125.,blend=.0)
    torch.save(weights,ROOT/'weights/recovery.pt')
    print('trained',len(y),len(pos),float(loss.detach().cpu()))
if __name__=='__main__':main()
