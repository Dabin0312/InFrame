"""Fit a shared visual encoder, then train matched 1-frame and 4-frame policies from the same demonstrations."""
import argparse, json, math, time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from policy import VisionPolicy, ROOT,WIDTH,HEIGHT
from prepare_data import supervision

SEED=531
def loss(pred,target):
    steer=F.smooth_l1_loss(pred[:,:2].contiguous(), target[:,:2].contiguous())
    distance=F.smooth_l1_loss(pred[:,2].contiguous(),target[:,2].contiguous())
    stop=F.binary_cross_entropy_with_logits(pred[:,3].contiguous(),target[:,3].contiguous())
    return 2.5*steer+.65*distance+.55*stop

def sample(rng,pools,count):
    # Rare turning/terminal views must contribute to both training objectives.
    sizes=(count//2,count//4,count//8)
    sets=[rng.choice(pool,n,replace=True) for pool,n in zip(pools,(*sizes,count-sum(sizes)))]
    return np.concatenate(sets)
def schedule(i,total,rate):
    return rate*(.1+.9*(1+math.cos(i/total*math.pi))/2)
def run(args):
    torch.manual_seed(SEED);torch.set_num_threads(4)
    device=torch.device(args.device)
    archive=np.load(args.data)
    images_all=[archive['images']]
    labels_all=[archive['labels']]
    times_all=[archive['time']]
    if args.views:
        for episode in archive['episodes']:
            with np.load(args.views/(str(episode)+'.npz')) as virtual:
                images_all.append(virtual['images'].reshape(-1,HEIGHT,WIDTH,3))
                actions=virtual['actions']
                for delta in virtual['offsets']:
                    labels_all.append(supervision(actions,delta))
                    times_all.append(np.arange(len(actions)))
    ims=torch.from_numpy(np.concatenate(images_all)).to(device);del images_all
    labels_np=np.concatenate(labels_all)
    ys=torch.from_numpy(labels_np).to(device)
    goals=torch.zeros(len(ys),device=device,dtype=torch.long)
    when=np.concatenate(times_all)
    assert len(archive['episodes'])==297
    angles=np.arctan2(labels_np[:,0],labels_np[:,1])
    pools=(np.arange(len(ys)),np.flatnonzero(np.abs(angles)>.22),np.flatnonzero((labels_np[:,2]<.9)&(labels_np[:,3]==0)),np.flatnonzero(labels_np[:,3]))
    model=VisionPolicy().to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
    rng=np.random.default_rng(SEED);logs=[];start=time.monotonic()
    for it in range(args.visual_steps):
        ids=torch.as_tensor(sample(rng,pools,args.batch),device=device)
        images=ims[ids]
        targets=ys[ids].clone()
        # Small common shifts mimic off-axis observations between teacher headings.
        k=int(rng.integers(-5,6)) if rng.random()<.5 else 0
        if k:
            xx=(torch.arange(WIDTH,device=device)-k).clamp(0,WIDTH-1)
            images=images.index_select(2,xx)
            delta=-math.atan(k/(WIDTH/2/math.tan(math.radians(39))))
            sine,cosine=targets[:,0].clone(),targets[:,1].clone()
            targets[:,0]=sine*math.cos(delta)+cosine*math.sin(delta)
            targets[:,1]=cosine*math.cos(delta)-sine*math.sin(delta)
        images=(images.float()*float(rng.uniform(.94,1.06))+float(rng.uniform(-4,4))).clamp(0,255)
        prediction=model(images[:,None],goals[ids])
        error=loss(prediction,targets);opt.zero_grad(set_to_none=True);error.backward()
        opt.param_groups[0]['lr']=schedule(it,args.visual_steps,.0014);opt.step()
        if it%100==0 or it+1==args.visual_steps:
            v=float(error.detach().cpu());logs.append(['encoder',it,v]);print('encoder',it,round(v,4),round(time.monotonic()-start,1),flush=True)
    torch.save({'history':1,'state':{k:v.detach().cpu() for k,v in model.state_dict().items()}},args.data.parent/'pretrained.pt')
    model.eval()
    with torch.no_grad():
        feats=[]
        for pics in ims.split(256):
            x=pics.clone().float().permute(0,3,1,2)/127.5-1
            feats.append(model.vision(x.contiguous(memory_format=torch.channels_last)))
        features=torch.cat(feats)
        indices=sample(np.random.default_rng(432),pools,128)
        pick=torch.as_tensor(indices,device=device)
        source=ims[pick].float()
        direct=model(source[:,None],goals[pick])
        encoded=model.vision((source.permute(0,3,1,2)/127.5-1).contiguous(memory_format=torch.channels_last))
        stored=features[pick]
        print('feature check',float((stored-encoded).abs().max()), 'direct_loss',float(loss(direct,ys[pick])),flush=True)
        assert torch.allclose(stored,encoded,atol=.003,rtol=.001), 'Feature cache mismatch'
        # The same samples must produce the same outputs in any batch order.
        shuffled=torch.randperm(len(pick)).to(device)
        delta=(direct[shuffled]-model(source[shuffled,None],goals[pick][shuffled])).abs().max().item()
        print('shuffle difference',delta,flush=True)
        assert delta < .02, 'Prediction depends on batch order' 
    torch.save({k:v.cpu() for k,v in model.vision.state_dict().items()},ROOT/'checkpoints'/'vision.pt')
    for h in [1,4]:
        # Same initialized heads, optimizer, minibatch sequence, stopping rule and encoder.
        torch.manual_seed(SEED+1);policy=VisionPolicy().to(device)
        policy.load_state_dict(model.state_dict())
        for p in policy.vision.parameters():p.requires_grad_(False)
        opt=torch.optim.AdamW([p for p in policy.parameters() if p.requires_grad],lr=.001,weight_decay=.001)
        rng=np.random.default_rng(SEED+1)
        hist_numpy=np.arange(len(when))[:,None]-np.minimum(when[:,None],np.arange(h-1,-1,-1)[None,:])
        hist=torch.from_numpy(hist_numpy).to(device)
        for it in range(args.head_steps):
            ids=torch.as_tensor(sample(rng,pools,128),device=device);x=features[hist[ids]]
            hx,_=policy.history(x)
            out=policy.head(torch.cat([x[:,-1],hx[:,-1],policy.goal(goals[ids])],1))
            error=loss(out,ys[ids]);opt.zero_grad(set_to_none=True);error.backward()
            opt.param_groups[0]['lr']=schedule(it,args.head_steps,.0015);opt.step()
            if it%400==0 or it+1==args.head_steps:
                v=float(error.detach().cpu());logs.append([f'h{h}',it,v]);print('head',h,it,round(v,4),flush=True)
        torch.save({'history':h,'state':{k:v.detach().cpu() for k,v in policy.state_dict().items()},'seed':SEED,'goals':['소화기']},ROOT/'checkpoints'/f'student-{h}.pt')
    (ROOT/'training.json').write_text(json.dumps(dict(seed=SEED,device=str(device),optimizer='AdamW',visual_steps=args.visual_steps,head_steps=args.head_steps,batch_visual=args.batch,
       batch_head=128,history_lengths=[1,4],training_rgb_views=len(ys),heading_augmentation=bool(args.views),trainable_parameters=sum(x.numel() for x in model.parameters()),logs=logs,seconds=time.monotonic()-start),indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('data',type=Path);parser.add_argument('--device',default='mps' if torch.backends.mps.is_available() else 'cpu')
    parser.add_argument('--visual-steps',type=int,default=3000);parser.add_argument('--head-steps',type=int,default=1400);parser.add_argument('--batch',type=int,default=96)
    parser.add_argument('--views',type=Path);run(parser.parse_args())
