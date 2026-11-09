"""Extend the reference-view index and retry missing IDs with visual evidence."""
import argparse, hashlib, json, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
import torch
from transformers import Sam2Model, Sam2Processor

BASE = Path(__file__).resolve().parents[2]/'InFrame_Fire_2단계'
sys.path.insert(0,str(BASE/'src'))
from geometry import assign, dump, keypoints, lift, localize, project, read_masks, MAP_IDS
from segment import photo, SAM_REV

AUDIT=[(s,i) for s in ['seq-03','seq-04'] for i in (33,213,393,573,753)]

def poses(path):
    result={}
    for t,*row in np.loadtxt(path):
        T=np.eye(4);T[:3,:3]=Rotation.from_quat(row[3:]).as_matrix();T[:3,3]=row[:3]
        result[round((t-1)*30)]=T
    return result

def build_index(scene, aux, assets, K, sift, orb):
    original=poses(BASE/'src/CameraTrajectory.txt')
    extra=poses(aux)
    # Match full SE(3) of overlapping camera poses; always retain the frozen map frame.
    overlap=sorted(set(original)&set(extra))
    if len(overlap)<10:raise ValueError('insufficient pose overlap')
    transforms=np.stack([original[i]@np.linalg.inv(extra[i]) for i in overlap])
    T=np.eye(4);T[:3,:3]=Rotation.from_matrix(transforms[:,:3,:3]).mean().as_matrix()
    T[:3,3]=np.median(transforms[:,:3,3],axis=0)
    overlap_error=[np.linalg.norm((T@extra[i])[:3,3]-original[i][:3,3]) for i in overlap]
    if np.median(overlap_error)>.05:raise ValueError('overlapping trajectories disagree')
    all_poses={i:original[i] for i in MAP_IDS}
    all_poses.update({i:T@p for i,p in extra.items() if i>=80})
    references=[];bank=[];sift_bank=[];obj_db={a['id']:[] for a in assets}
    for i,P in sorted(all_poses.items()):
        stem=scene/'seq-01'/f'frame-{i:06}'
        rgb=np.array(Image.open(stem.with_suffix('.color.png')).convert('RGB'))
        depth=cv2.imread(str(stem.with_suffix('.depth.png')),-1)/1000
        xy,d=keypoints(rgb,sift);u,v=np.rint(xy).astype(int).T;z=depth[v,u];good=(z>.15)&(z<6)
        xy=xy[good];d=d[good];u=u[good];v=v[good]
        world=np.float32(lift(xy,z[good],P,K))
        idx=cv2.FlannBasedMatcher(dict(algorithm=1,trees=4),dict(checks=32));idx.add([d]);idx.train()
        references.append((i,world,idx))
        if i not in MAP_IDS:continue
        sift_bank.append((i,world,d))
        ox,od=keypoints(rgb,orb);ou,ov=np.rint(ox).astype(int).T;oz=depth[ov,ou];ok=(oz>.15)&(oz<6)
        bank.append((i,np.float32(lift(ox[ok],oz[ok],P,K)),od[ok]))
        key=f'seq-01_{i:06}';_,masks=read_masks(BASE/'masks',key)
        for asset in assets:
            obs=next((o for o in asset['registrations'] if o['frame']==key),None)
            if obs is None:continue
            m=cv2.erode(masks[obs['mask_index']].astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
            sel=m[v,u];obj_db[asset['id']].append((d[sel],world[sel]))
    diag={'fixed_frames':MAP_IDS,'extra_reference_frames':[i for i in all_poses if i>=80],
          'map_from_aux':T.tolist(),'median_overlap_m':float(np.median(overlap_error))}
    return references, bank, sift_bank, obj_db, diag

def rescue_pose(xy,desc,refs,K):
    if desc is None:return None
    cv2.setRNGSeed(13); candidates=[]
    for fid,world,index in refs:
        pairs=index.knnMatch(desc,k=2)
        hits=sorted((a for a,b in pairs if a.distance<.77*b.distance),key=lambda m:m.distance)
        unique={}
        for m in hits:unique.setdefault(m.trainIdx,m.queryIdx)
        if len(unique)<22:continue
        pts=world[list(unique)];pix=xy[list(unique.values())]
        ok,r,t,inliers=cv2.solvePnPRansac(pts,pix,K,None,iterationsCount=220,reprojectionError=3,flags=cv2.SOLVEPNP_EPNP)
        if not ok or inliers is None or len(inliers)<22:continue
        ids=inliers.ravel();hh=cv2.convexHull(pix[ids])
        if cv2.contourArea(hh)<.035*640*480:continue
        r,t=cv2.solvePnPRefineLM(pts[ids],pix[ids],K,None,r,t)
        est=cv2.projectPoints(pts[ids],r,t,K,None)[0][:,0]
        err=float(np.median(np.linalg.norm(est-pix[ids],axis=1)))
        if err>2.5:continue
        cam=np.eye(4);cam[:3,:3]=cv2.Rodrigues(r)[0];cam[:3,3]=t.ravel()
        candidates.append((len(ids),-err,fid,np.linalg.inv(cam)))
    for n,neg,i,P in sorted(candidates,key=lambda a:-a[0]):
        for _,_,j,Q in candidates:
            if j!=i and np.linalg.norm(Q[:3,3]-P[:3,3])<.12 and Rotation.from_matrix(P[:3,:3].T@Q[:3,:3]).magnitude()<np.deg2rad(6):
                return n,neg,i,P
    return None

def confirm(rgb, pose, xy, desc, track, db, K, sp, model):
    # The projected box is only a prompt. Require multiple photo-local matches on the registered object.
    if desc is None:return None
    uv,z=project(track['support'],pose,K);uv=uv[z>.1]
    if not len(uv):return None
    h,w=rgb.shape[:2];lo=np.maximum(np.quantile(uv,.015,axis=0)-5,[0,0]);hi=np.minimum(np.quantile(uv,.985,axis=0)+5,[w-1,h-1])
    if min(hi-lo)<15:return None
    matcher=cv2.BFMatcher(cv2.NORM_L2);matches={}
    for rd,world in db:
        if not len(rd):continue
        projected,_=project(world,pose,K)
        for a,b in matcher.knnMatch(rd,desc,k=2):
            p=xy[a.trainIdx]
            if a.distance>=.77*b.distance or np.linalg.norm(p-projected[a.queryIdx])>12:continue
            if np.all(p>=lo) and np.all(p<=hi):
                matches[tuple(np.rint(p/3).astype(int))]=p
    points=np.array(list(matches.values()))
    if len(points)<4 or max(np.ptp(points,axis=0))<13:return None
    inp=sp(images=Image.fromarray(rgb),input_boxes=[[np.r_[lo,hi].tolist()]],return_tensors='pt')
    with torch.inference_mode():
        res=model(**inp,multimask_output=False)
    mask=sp.post_process_masks(res.pred_masks,inp.original_sizes)[0][0,0].numpy().astype(bool)
    u,v=np.rint(points).astype(int).T
    if mask[v,u].sum()<4 or mask[v,u].mean()<.70:return None
    return mask,dict(box_xyxy=np.r_[lo,hi].tolist(),method='map_prompt_SAM2_and_verified_SIFT',matched_points=int(mask[v,u].sum()),mask_pixels=int(mask.sum()))

def main():
    parser=argparse.ArgumentParser()
    for a in ['scene','controls','audit_masks','out','trajectory']:parser.add_argument(a,type=Path)
    parser.add_argument('--sam',default='facebook/sam2.1-hiera-tiny')
    a=parser.parse_args();out=a.out;out.mkdir(exist_ok=True,parents=True);cache=out/'masks';cache.mkdir(exist_ok=True)
    torch.set_num_threads(5);cv2.setNumThreads(3)
    sp=Sam2Processor.from_pretrained(a.sam,revision=SAM_REV);model=Sam2Model.from_pretrained(a.sam,revision=SAM_REV).eval()
    obj=json.loads((BASE/'map.json').read_text());K=np.array(obj['K']);surface=np.load(BASE/'scene.npz')
    tracks=[dict(id=o['id'],support=surface['support_'+o['id']]) for o in obj['objects']]
    sift=cv2.SIFT_create(nfeatures=2200);orb=cv2.ORB_create(nfeatures=2200)
    refs,bank,sb,db,diag=build_index(a.scene,a.trajectory,obj['objects'],K,sift,orb);dump(out/'index.json',diag)
    old=json.loads((BASE/'links.json').read_text());oldkeys={r['photo'] for r in old}
    rows=old+[dict(photo=f'{s}_{i:06}',links=[],localized=False) for s,i in AUDIT]
    base_audit=[]
    for row in rows:
        key=row['photo'];part=key.split('_');fresh=key not in oldkeys
        path=(a.controls/(key+'.png')) if key.startswith('control_') else photo(a.scene,part[0],int(part[1]))
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if not fresh:assert digest==row['sha256']
        row['sha256']=digest;rgb=np.array(Image.open(path).convert('RGB'));xy,desc=keypoints(rgb,sift)
        meta,masks=read_masks(a.audit_masks if fresh else BASE/'masks',key)
        if fresh:
            e=localize(rgb,bank,K,orb,cv2.BFMatcher(cv2.NORM_HAMMING)) or localize(rgb,sb,K,sift,cv2.BFMatcher(cv2.NORM_L2),True)
            if e:
                n,err,idx,P=e;row.update(localized=True,pose_c2w=P.tolist(),inliers=n,median_reprojection_px=-err,keyframe=idx,links=assign(tracks,masks,P,K))
            base_audit.append(json.loads(json.dumps(row)))
        if not row['localized']:
            est=rescue_pose(xy,desc,refs,K)
            if est is not None:
                n,err,idx,P=est;row.update(localized=True,pose_c2w=P.tolist(),inliers=n,median_reprojection_px=-err,keyframe=idx,feature_method='expanded_SIFT_PnP_consensus',links=assign(tracks,masks,P,K))
        if row['localized']:
            P=np.array(row['pose_c2w']);registered={l['id'] for l in row['links']}
            for track in tracks:
                if track['id'] in registered:continue
                candidate=confirm(rgb,P,xy,desc,track,db[track['id']],K,sp,model)
                if candidate is None:continue
                mask,details=candidate
                links=assign(tracks,mask[None],P,K)
                if len(links)!=1 or links[0]['id']!=track['id']:continue
                if any((mask & masks[l['mask_index']]).sum()/max(1,(mask | masks[l['mask_index']]).sum())>.45 for l in row['links']):continue
                links[0]['mask_index']=len(masks);row['links']+=links
                meta.append(details);masks=np.concatenate((masks,mask[None]))
        row['detections']=meta;row['status']='linked' if row['links'] else ('no_confirmed_instance' if row['localized'] else 'unlocalized')
        dump(cache/(key+'.json'),meta);np.savez_compressed(cache/(key+'.npz'),masks=np.packbits(masks,axis=-1))
    dump(out/'links.json',rows);dump(out/'audit_baseline.json',base_audit)

if __name__=='__main__':main()
