"""Fit the temporal action head from manually labelled real RGB. Requires torch, numpy, onnx."""
import argparse,json,hashlib
from pathlib import Path
import torch, numpy as np
from torch import nn
from torch.nn import functional as F
HERE=Path(__file__).resolve().parent
N=8
def features(p):
    score,x,y,w,h=p.unbind(-1)
    return torch.stack([score,score*w,score*h,score*abs(x-.5),score*abs(y-.5),w*h*score,score.sqrt()*h,score.square()],-1)
class StopHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer('mean',torch.zeros(N));self.register_buffer('scale',torch.ones(N))
        self.linear=nn.Linear(N*2,1)
    def forward(self,seq):
        z=(seq-self.mean)/self.scale
        return self.linear(torch.cat([z[:,-1],z.mean(dim=1)],1))[:,0]
class Action(nn.Module):
    def __init__(self,head):super().__init__();self.head=head
    def forward(self,boxes,memory,base,dock):
        ix=boxes[:,4].argmax(dim=1)
        v=boxes[0,:,ix[0]];cx,cy,w,h,score=v.unbind()
        p=torch.stack([score,cx/320,(cy-40)/240,w/320,h/240])
        f=features(p)[None,None]
        previous=torch.where(memory[0,0,0]<0,f.expand(1,3,N),memory)
        seq=torch.cat([previous,f],dim=1)
        semantic=self.head(seq)
        regular=(base[:,3]>=0)&((torch.exp(base[:,2].clamp(0,4))-1)<=.65)
        aligned=(dock[:,0]>1)&(dock[:,1]>.9)
        return seq[:,1:],regular|aligned|(semantic>=0),semantic,p
def fit(directory,out):
    torch.manual_seed(12);torch.set_num_threads(1)
    split=json.loads((HERE/'split.json').read_text());ann=json.loads((HERE/'annotations.json').read_text())
    def sequences(ids):
        result=[]
        for name in ids:
            rows=json.loads((directory/(name+'.json')).read_text())
            f=features(torch.tensor([r['proposal'] for r in rows]))
            seq=torch.stack([torch.stack([f[max(0,i-j)] for j in [3,2,1,0]]) for i in range(len(f))])
            t=np.array([r['t'] for r in rows])
            def mask(intervals):return np.array([any(a<=v<=b for a,b in intervals) for v in t])
            result.append((name,seq,torch.tensor(mask(ann['positive'][name]),dtype=torch.float32),~mask(ann['ignore'].get(name,[]))))
        return result
    train=sequences(split['train']);dev=sequences(split['dev']);net=StopHead()
    X=torch.cat([s[m] for _,s,_,m in train]);y=torch.cat([y[m] for _,_,y,m in train]);net.mean.copy_(X[:,-1].mean(0));net.scale.copy_(X[:,-1].std(0).clamp(min=.02))
    opt=torch.optim.AdamW(net.parameters(),lr=.012,weight_decay=.04)
    for _ in range(380):
        pred=net(X);loss=F.binary_cross_entropy_with_logits(pred,y,pos_weight=((1-y).sum()/y.sum()).sqrt())+.004*net.linear.weight.square().sum();opt.zero_grad();loss.backward();opt.step()
    # Select an operating point with complete episodes and a cost for premature first STOPs.
    scores=[]
    with torch.no_grad():
        for threshold in np.arange(-2.,3.51,.25):
            correct=early=miss=0
            for name,seq,target,_ in dev:
                hits=torch.where(net(seq)>=threshold)[0]
                if len(hits) and target[hits[0]]==1:correct+=1
                elif len(hits):early+=1
                elif target.any():miss+=1
                else:correct+=1
            scores.append((correct-2*early-miss,-abs(float(threshold)),float(threshold)))
        threshold=max(scores)[2];net.linear.bias.sub_(threshold)
    out.mkdir(exist_ok=True,parents=True);torch.save(net.state_dict(),out/'head.pt')
    model=Action(net).eval()
    args=(torch.zeros(1,5,2100),torch.zeros(1,3,N),torch.zeros(1,4),torch.zeros(1,4))
    torch.onnx.export(model,args,str(out/'decision.onnx'),input_names=['boxes','memory','base','dock'],output_names=['next_memory','policy_stop','stop_logit','observation'],opset_version=17,dynamo=False)
    audit={'fit_episodes':len(train),'development_episodes':len(dev),'labelled_frames':len(y),'positive_frames':int(y.sum()),'threshold_shift':threshold,'dev':{}}
    for name,seq,labels,_ in dev:
        hits=torch.where(net(seq)>=0)[0];audit['dev'][name]={'t':float(hits[0])/4 if len(hits) else None,'valid':bool(labels[hits[0]]) if len(hits) else None}
    (out/'fit.json').write_text(json.dumps(audit,indent=2));print(audit)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('features',type=Path);p.add_argument('out',type=Path);args=p.parse_args();fit(args.features,args.out)
