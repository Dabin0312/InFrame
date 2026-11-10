"""Fit H4 on Castle demonstrations and counterfactual names; split by complete sequence."""
import json,argparse,hashlib
from pathlib import Path
import numpy as np, torch
from torch.nn import functional as F
from model import GoalH4
def main():
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('parent');p.add_argument('out',type=Path)
    p.add_argument('--extra',type=Path);p.add_argument('--epochs',type=int,default=42);p.add_argument('--device',default='mps');a=p.parse_args()
    torch.manual_seed(94);rng=np.random.default_rng(94);torch.set_num_threads(4);device=a.device
    parts=[np.load(a.data)]+([np.load(a.extra)] if a.extra else [])
    data={k:np.concatenate([q[k] for q in parts]) for k in ('rgb','labels','det','truth','sweep')}
    data.update(emb=parts[0]['emb'],names=parts[0]['names'])
    n=len(data['rgb']);order=np.random.default_rng(314).permutation(n);nv=max(1,n//10);val,train=order[:nv],order[nv:]
    rgb=torch.from_numpy(data['rgb']).to(device);truth=torch.from_numpy(data['truth']).to(device)
    obs=torch.from_numpy(data['det']).to(device);labels=torch.from_numpy(data['labels']).to(device);emb=torch.from_numpy(data['emb']).to(device)
    yy,xx=torch.meshgrid((torch.arange(15,device=device)+.5)/15,(torch.arange(20,device=device)+.5)/20,indexing='ij')
    sweep=torch.from_numpy(data['sweep']).long().to(device)
    # Align both collection profiles to one physical STOP target.
    labels[:,:,:3]=torch.where((labels[:,:,:3]==3)&(truth[...,5]>1.03),0,labels[:,:,:3])
    invisible=torch.ones_like(labels,dtype=torch.bool);invisible[:,:,:3]=truth[:,:,:,0]==0
    labels=torch.where(invisible,sweep[:,:,None],labels)
    m=truth[...,None,None];mask=((abs(m[:,:,:,1]-xx)<=m[:,:,:,3]/2+.009)&(abs(m[:,:,:,2]-yy)<=m[:,:,:,4]/2+.012)&(m[:,:,:,0]>0)).float()
    net=GoalH4(emb[:3].cpu(),a.parent).to(device)
    opt=torch.optim.AdamW(net.parameters(),lr=.0012,weight_decay=.001)
    a.out.mkdir(parents=True,exist_ok=True);best=0.;stats=[]
    for epoch in range(a.epochs):
        net.train();losses=[];opt.param_groups[0]['lr']=.00035 if epoch>=a.epochs*.7 else .0012
        for batch in np.array_split(rng.permutation(train),int(np.ceil(len(train)/48))):
            idx=torch.as_tensor(batch,device=device);b=len(batch);raw=rgb[idx]
            f,grid=net.encode(raw);y=mask[idx]
            focal=(torch.sigmoid(grid).detach()-y).abs().square()*F.binary_cross_entropy_with_logits(grid,y,reduction='none')
            seg=(focal*y).sum()/y.sum().clamp(min=1)+(focal*(1-y)).mean()
            # Identical observations, counterfactual text. Include a genuinely absent concept with every sequence.
            goals=torch.cat((torch.arange(3,device=device).expand(b,-1),torch.randint(3,emb.shape[0],(b,1),device=device)),1)
            idx2=idx[:,None].expand_as(goals).reshape(-1);g=goals.flatten()
            o=obs[idx2,:,g].clone();gt=truth[idx]
            # Random loss of proposals prevents a single detector score deciding an action.
            keep=(torch.rand(len(g),4,1,device=device)>.10).float();o=o*keep
            logits=net.decision(f.repeat_interleave(4,0),grid.repeat_interleave(4,0),emb[g],o)
            label=labels[idx2,:,g];weights=torch.tensor([1.8,.65,2.0,2.5],device=device)
            search_loss=F.cross_entropy(net.search(f).flatten(0,1),sweep[idx].flatten(),weight=torch.tensor([1.8,1.],device=device))
            loss=F.cross_entropy(logits.flatten(0,1),label.flatten(),weight=weights)+seg*1.4+search_loss*.50
            opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),4);opt.step()
            losses.append(float(loss.detach().cpu()))
        net.eval();conf=np.zeros((4,4),int)
        with torch.no_grad():
            for batch in np.array_split(val,int(np.ceil(len(val)/40))):
                idx=torch.as_tensor(batch,device=device);f,grid=net.encode(rgb[idx])
                for k in [0,1,2,3,4]:
                    logits=net.decision(f,grid,emb[k:k+1].expand(len(idx),-1),obs[idx,:,k]);pred=logits[:,-1].argmax(1).cpu().numpy()
                    np.add.at(conf,(labels[idx,-1,k].cpu().numpy(),pred),1)
        acc=np.diag(conf)/np.maximum(conf.sum(1),1);metric=acc.mean()
        stats.append(dict(epoch=epoch+1,recall=acc.tolist(),confusion=conf.tolist(),loss=float(np.mean(losses))))
        if metric>best:
            best=metric;torch.save(net.state_dict(),a.out/'student.pt');best_epoch=epoch+1
        print(epoch+1,round(np.mean(losses),3),acc.round(3),flush=True)
    net.cpu().load_state_dict(torch.load(a.out/'student.pt',weights_only=True,map_location='cpu'));net.eval()
    torch.onnx.export(net,(rgb[0:1].cpu(),emb[0:1].cpu(),obs[0:1,:,0].cpu()),str(a.out/'student.onnx'),
                      input_names=['rgb','goal_embedding','rgb_goal_proposals'],output_names=['action_logits'],opset_version=17,dynamo=False)
    (a.out/'fit.json').write_text(json.dumps(dict(parent_sha256=hashlib.sha256(Path(a.parent).read_bytes()).hexdigest(),training_sequences=len(train),
        validation_sequences=len(val),seed=94,split_seed=314,selected_epoch=best_epoch,validation=stats[best_epoch-1],names=data['names'].tolist()),indent=2))
if __name__=='__main__':main()
