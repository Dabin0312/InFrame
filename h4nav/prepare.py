"""Extract training-only visual supervision from collect.mjs output and frozen YOLOE."""
import argparse,json
from pathlib import Path
import numpy as np, torch, cv2
from ultralytics import YOLOE
import clip
NAMES=['chair','trash can','fire extinguisher','toaster','bicycle','teddy bear','refrigerator','coffee maker']
def main():
 p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('weights');p.add_argument('encoder');p.add_argument('--device',default='mps');a=p.parse_args()
 records=[json.loads(s) for s in (a.data/'labels.ndjson').read_text().splitlines()];n=len(records);torch.set_num_threads(4)
 enc=torch.jit.load(a.encoder,map_location='cpu').eval()
 with torch.inference_mode():emb=enc(clip.tokenize(NAMES)).numpy()
 net=YOLOE(a.weights);net.set_classes(NAMES,net.get_text_pe(NAMES));imgs=np.empty((n,4,60,80,3),np.uint8)
 det=np.zeros((n,4,len(NAMES),5),np.float32)
 truth=np.zeros((n,4,3,6),np.float32);labels=np.zeros((n,4,len(NAMES)),np.int64);labels.fill(1)
 keys=[]
 for i,rec in enumerate(records):
  for t,row in enumerate(rec['rows']):
   keys.append((i,t,a.data/f"{rec['i']}-{t}.jpg"))
   for k,v in enumerate(row['vis']):
    x,y,x2,y2=v['box'];cx=(x+x2)/320;cy=(y+y2)/240
    if v['pixels']<6:continue
    truth[i,t,k]=[1,cx,cy,(x2-x+1)/160,(y2-y+1)/120,row['distances'][k]]
    labels[i,t,k]=1 if cx<.37 else 2 if cx>.63 else 3 if row['distances'][k]<=1.13 and v['pixels']>=56 else 0
 for j in range(0,len(keys),24):
  batch=keys[j:j+24];rgb=[cv2.imread(str(f)) for _,_,f in batch]
  res=net.predict(rgb,device=a.device,imgsz=416,rect=False,conf=.245,verbose=False)
  for (i,t,_),im,r in zip(batch,rgb,res):
   imgs[i,t]=cv2.resize(im[:,:,::-1],(80,60),interpolation=cv2.INTER_AREA)
   for c,score,box in zip(r.boxes.cls.cpu().tolist(),r.boxes.conf.cpu().tolist(),r.boxes.xywhn.cpu().tolist()):
    k=int(c)
    if score>det[i,t,k,0]:det[i,t,k]=[score,*box]
  if j%480==0:print('examples',j,'/',len(keys),flush=True)
 np.savez(a.data/'train.npz',rgb=imgs,det=det,truth=truth,labels=labels,emb=emb,names=NAMES,sweep=np.array([[f['sweep'] for f in r['rows']] for r in records]))
if __name__=='__main__':main()
