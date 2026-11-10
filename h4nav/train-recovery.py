"""Train H4 motion memory on independent randomized Castle sequences."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from model import GoalH4
from recovery import MotionMemory, RecoveryH4

def main():
    p=argparse.ArgumentParser()
    p.add_argument('sequences',type=Path);p.add_argument('parent',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--epochs',type=int,default=95)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    torch.manual_seed(245);torch.set_num_threads(4)
    rows=[s['rows'] for s in json.loads(a.sequences.read_text())]
    prev=torch.tensor([[r['prev']+1 for r in seq] for seq in rows])
    prev=F.one_hot(prev,4).float()
    delta=torch.tensor([[r['diff'] for r in seq] for seq in rows],dtype=torch.float32)
    labels=torch.tensor([[r['label'] for r in seq] for seq in rows])
    order=np.random.default_rng(218).permutation(len(rows))
    val,train=order[:len(rows)//8],order[len(rows)//8:]
    net=MotionMemory();optimizer=torch.optim.AdamW(net.parameters(),lr=.006)
    best=-1; filename=a.out/'motion.pt'
    for epoch in range(a.epochs):
        net.train()
        if epoch==int(.72*a.epochs): optimizer.param_groups[0]['lr']=.002
        for batch in torch.randperm(len(train)).split(32):
            idx=train[batch.numpy()];d=delta[idx]
            # Small photometric noise in otherwise stationary observations.
            d=(d*(.85+.30*torch.rand_like(d)) + .20*torch.rand_like(d)).clamp(min=0)
            scores,_=net(prev[idx],d,torch.zeros(1,len(idx),net.width))
            loss=F.cross_entropy(scores.flatten(0,1),labels[idx].flatten(),weight=torch.tensor([.65,1.4,1.3,1.5]))
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),3);optimizer.step()
        with torch.no_grad():
            scores,_=net(prev[val],delta[val],torch.zeros(1,len(val),net.width))
            predicted=scores.argmax(-1);target=labels[val]
            recalls=[(predicted[target==k]==k).float().mean().item() for k in range(4)]
            metric=np.mean(recalls)
            if metric>best:
                best=metric;best_epoch=epoch+1;best_recall=recalls
                torch.save(net.state_dict(),filename)
        if epoch%8==0: print(epoch+1,recalls,flush=True)
    net.load_state_dict(torch.load(filename,weights_only=True))
    state=torch.load(a.parent,map_location='cpu',weights_only=True)
    base=GoalH4(state['prototypes']);base.load_state_dict(state)
    model=RecoveryH4(base,net).eval()
    samples=(torch.zeros(1,4,60,80,3,dtype=torch.uint8),torch.ones(1,512),torch.zeros(1,4,5),
             torch.tensor([[1.,0.,0.,0.]]),torch.zeros(1,1,net.width))
    names=['rgb','goal_embedding','rgb_goal_proposals','previous_action','memory']
    onnx=a.out/'student.onnx'
    torch.onnx.export(model,samples,str(onnx),input_names=names,output_names=['action_logits','next_memory'],opset_version=17,dynamo=False)
    print('selected',best_epoch,best_recall,flush=True)
    (a.out/'recovery-fit.json').write_text(json.dumps(dict(sequence_seed=303819,split_seed=218,train=len(train),validation=len(val),steps_per_sequence=len(rows[0]),
        selected_epoch=best_epoch,valid_recall_keep_forward_left_right=best_recall,
        parent_pt_sha256=hashlib.sha256(a.parent.read_bytes()).hexdigest(),onnx_sha256=hashlib.sha256(onnx.read_bytes()).hexdigest()),indent=2)+'\n')
if __name__=='__main__':main()
