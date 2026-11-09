"""Metric Fire semantic map and RGB-only photo links. No evaluation labels or query depth."""
from pathlib import Path
import argparse, hashlib, json
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation
from PIL import Image

MAP_IDS = list(range(0,80,10))
OBJECT_GATE_M = .13
MIN_SUPPORT = .32
MIN_MARGIN = .15

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def project(points, pose, K):
    cam = np.einsum('ni,ij->nj',points-pose[:3,3],pose[:3,:3])
    uvw = np.einsum('ni,ji->nj',cam,K)
    return uvw[:,:2]/np.maximum(uvw[:,2:], 1e-6), cam[:,2]

def lift(xy, depths, pose, K):
    rays = np.einsum('ni,ji->nj',np.c_[xy,np.ones(len(xy))],np.linalg.inv(K))
    return np.einsum('ni,ji->nj',rays * depths[:,None],pose[:3,:3]) + pose[:3,3]

def metric_sample(mask, depth, pose, K, stride):
    v,u = np.where(mask & (depth > .15) & (depth < 6))
    ids = np.arange(0,len(v),stride)
    return lift(np.c_[u[ids],v[ids]], depth[v[ids],u[ids]], pose,K), (v[ids],u[ids])

def read_masks(cache,key,width=640):
    data = json.loads((cache/(key+'.json')).read_text())
    with np.load(cache/(key+'.npz')) as z:
        masks = np.unpackbits(z['masks'], axis=-1)[...,:width].astype(bool)
    return data,masks

def keypoints(image,orb):
    k,d = orb.detectAndCompute(cv2.cvtColor(image,cv2.COLOR_RGB2GRAY),None)
    return np.float32([kp.pt for kp in k]).reshape(-1,2),d

def localize(image,bank,K,orb,matcher,require_consensus=False):
    # Query descriptors and RGB are the only inputs from the revisit capture.
    xy,desc = keypoints(image,orb)
    candidates = []
    if desc is None: return None
    cv2.setRNGSeed(7)
    for i,world,ref in bank:
        pairs = matcher.knnMatch(desc,ref,k=2)
        matches = sorted((a for p in pairs if len(p)==2 for a,b in [p] if a.distance < .75*b.distance),key=lambda m:m.distance)
        unique = {}
        for m in matches: unique.setdefault(m.trainIdx,m.queryIdx)
        if len(unique)<20: continue
        pts = world[list(unique)]
        pix = xy[list(unique.values())]
        ok,r,t,sel = cv2.solvePnPRansac(pts,pix,K,None,iterationsCount=150,reprojectionError=3,flags=cv2.SOLVEPNP_EPNP)
        if not ok or sel is None or len(sel)<20: continue
        ids=sel.ravel()
        r,t = cv2.solvePnPRefineLM(pts[ids],pix[ids],K,None,r,t)
        reproj=cv2.projectPoints(pts[ids],r,t,K,None)[0][:,0]
        err=float(np.median(np.linalg.norm(reproj-pix[ids],axis=1)))
        if err>=3: continue
        view = np.eye(4)
        view[:3,:3]=cv2.Rodrigues(r)[0]
        view[:3,3]=t.ravel()
        entry=(len(ids),-err,i,np.linalg.inv(view))
        candidates.append(entry)
    for candidate in sorted(candidates,key=lambda e:e[:2],reverse=True):
        if not require_consensus:
            return candidate
        pose=candidate[-1]
        for other in candidates:
            if other[2]==candidate[2]:continue
            offset=np.linalg.norm(pose[:3,3]-other[-1][:3,3])
            rotation=Rotation.from_matrix(pose[:3,:3].T @ other[-1][:3,:3]).magnitude()
            if offset<.10 and rotation<np.deg2rad(5):return candidate
    return None

def robust_surface(mask,depth,pose,K):
    inner=cv2.erode(mask.astype('uint8'),np.ones((5,5),'uint8')).astype(bool)
    z=depth[inner & (depth>.15) & (depth<6)]
    if len(z)<80:return None
    med=np.median(z)
    clean=inner & (np.abs(depth-med)<.09)
    pts,_=metric_sample(clean,depth,pose,K,8)
    if len(pts)<10:return None
    return pts

def update_tracks(tracks, detections, key):
    centers=[np.median(d['points'],axis=0) for d in detections]
    used=set()
    if tracks and centers:
        previous=np.array([np.median(t['centers'],axis=0) for t in tracks])
        costs=np.linalg.norm(previous[:,None]-np.array(centers)[None],axis=2)
        pairs=linear_sum_assignment(np.where(costs<=OBJECT_GATE_M,costs,100.))
        for t,j in zip(*pairs):
            if costs[t,j] > OBJECT_GATE_M: continue
            used.add(j)
            track=tracks[t]
            track['centers'].append(centers[j])
            track['points'].append(detections[j]['points'])
            track['observations'].append({'frame':key,**detections[j]['meta']})
    for j,d in enumerate(detections):
        if j not in used:
            tracks.append(dict(centers=[centers[j]],points=[d['points']],observations=[{'frame':key,**d['meta']}]))

def assign(tracks, masks, pose, K):
    if not len(masks) or not tracks: return []
    h,w=masks.shape[-2:]
    support=np.zeros((len(tracks),len(masks)))
    precision=np.zeros_like(support)
    for i,t in enumerate(tracks):
        uv,z=project(t['support'],pose,K)
        xy=np.rint(uv).astype(int)
        inside=(z>0)&(xy[:,0]>=0)&(xy[:,0]<w)&(xy[:,1]>=0)&(xy[:,1]<h)
        x,y=xy[inside].T
        if len(x)<.18*len(uv):continue
        # Full-map denominator prevents tiny visible fragments from confirming an asset.
        support[i]=masks[:,y,x].sum(axis=1)/len(uv)
        silhouette=np.zeros((h,w),np.uint8)
        hull=cv2.convexHull(xy[inside].astype(np.int32))
        cv2.fillConvexPoly(silhouette,hull,1)
        silhouette=cv2.dilate(silhouette,np.ones((15,15),np.uint8)).astype(bool)
        precision[i]=(masks & silhouette).sum(axis=(1,2))/np.maximum(1,masks.sum(axis=(1,2)))
    score=2*support*precision / np.maximum(1e-9,support+precision)
    eligible=(support>=MIN_SUPPORT) & (precision>=.50)
    for i,j in zip(*np.where(eligible)):
        other=np.delete(score[:,j],i)
        if len(other) and score[i,j]-np.max(other)<MIN_MARGIN:eligible[i,j]=False
    rows,cols=linear_sum_assignment(np.where(eligible,-score,10))
    return [{'id':tracks[i]['id'],'mask_index':int(j),'support_fraction':round(float(support[i,j]),4),'silhouette_precision':round(float(precision[i,j]),4)}
            for i,j in zip(rows,cols) if eligible[i,j]]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('scene',type=Path);p.add_argument('cache',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--controls',type=Path);p.add_argument('--trajectory',type=Path,default=Path(__file__).with_name('CameraTrajectory.txt'))
    args=p.parse_args()
    out=args.out;out.mkdir(exist_ok=True,parents=True)
    K=np.loadtxt(args.scene/'camera-intrinsics.txt')
    orb=cv2.ORB_create(nfeatures=2200);matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    trajectory=np.loadtxt(args.trajectory)
    poses={}
    for ts,x,y,z,qx,qy,qz,qw in trajectory:
        pose=np.eye(4);pose[:3,:3]=Rotation.from_quat([qx,qy,qz,qw]).as_matrix();pose[:3,3]=[x,y,z]
        poses[round((ts-1)*30)]=pose
    sift=cv2.SIFT_create(nfeatures=2200);sift_matcher=cv2.BFMatcher(cv2.NORM_L2)
    tracks=[];bank=[];sift_bank=[];scene_pts=[];scene_rgb=[]
    for i in MAP_IDS:
        key=f'seq-01_{i:06}'; stem=f'frame-{i:06}'
        image=np.array(Image.open(args.scene/'seq-01'/(stem+'.color.png')).convert('RGB'))
        depth=cv2.imread(str(args.scene/'seq-01'/(stem+'.depth.png')),cv2.IMREAD_UNCHANGED)/1000.
        pose=poses[i]
        for extractor,target in [(orb,bank),(sift,sift_bank)]:
            xy,desc=keypoints(image,extractor)
            u,v=np.rint(xy).astype(int).T; ds=depth[v,u]; good=(ds>.15)&(ds<6)
            target.append((i,np.float32(lift(xy[good],ds[good],pose,K)),desc[good]))
        grid=np.zeros_like(depth,dtype=bool);grid[::6,::6]=True
        cloud,(v,u)=metric_sample(grid,depth,pose,K,1);scene_pts.append(cloud);scene_rgb.append(image[v,u])
        meta,masks=read_masks(args.cache,key)
        detections=[]
        for j,(m,mk) in enumerate(zip(meta,masks)):
            pts=robust_surface(mk,depth,pose,K)
            if pts is not None:detections.append(dict(points=pts,meta={'mask_index':j,**m}))
        update_tracks(tracks,detections,key)
    tracks=[t for t in tracks if len(t['observations'])>=3]
    tracks.sort(key=lambda t: np.median(t['centers'],axis=0)[0])
    rng=np.random.default_rng(7)
    assets=[]
    for i,t in enumerate(tracks):
        t['id']=chr(ord('A')+i);allpts=np.concatenate(t['points'])
        t['support']=allpts[rng.choice(len(allpts),min(1800,len(allpts)),replace=False)]
        center=np.median(t['centers'],axis=0)
        assets.append(dict(id=t['id'],surface_anchor_xyz_m=center.tolist(),
            observation_spread_m=float(np.median(np.linalg.norm(np.array(t['centers'])-center,axis=1))),
            registrations=t['observations']))
    dump(out/'map.json',dict(scene='7-scenes-fire',coordinate_system='ORB-SLAM3 first camera: +x right, +y down, +z forward; metres',K=K.tolist(),objects=assets))
    np.savez_compressed(out/'scene.npz',xyz=np.float32(np.concatenate(scene_pts)),rgb=np.concatenate(scene_rgb),
        camera_xyz=np.float32(trajectory[:,1:4]),**{'support_'+t['id']:np.float32(t['support']) for t in tracks})
    paths=[(f'{s}_{i:06}',args.scene/s/f'frame-{i:06}.color.png') for s,ids in [('seq-02',list(range(0,80,10))+list(range(100,1000,100))),('seq-03',range(0,1000,90)),('seq-04',sorted([*range(0,1000,125),*range(60,1000,125)]))] for i in ids]
    if args.controls:paths += [(p.stem,p) for p in sorted(args.controls.glob('*.png'))]
    records=[]
    for key,path in paths:
        image=np.array(Image.open(path).convert('RGB'));meta,masks=read_masks(args.cache,key,image.shape[1])
        record=dict(photo=key,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),detections=meta,links=[],localized=False)
        est=localize(image,bank,K,orb,matcher)
        method='ORB'
        if est is None:
            est=localize(image,sift_bank,K,sift,sift_matcher,require_consensus=True)
            method='SIFT'
        if est is not None:
            n,err,ref,pose=est
            record.update(localized=True,feature_method=method,keyframe=ref,pose_c2w=pose.tolist(),inliers=n,median_reprojection_px=-err,links=assign(tracks,masks,pose,K))
        record['status']='linked' if record['links'] else ('no_confirmed_instance' if record['localized'] else 'unlocalized')
        records.append(record)
    dump(out/'links.json',records)
    print('Registered', [(a['id'],len(a['registrations']),a['surface_anchor_xyz_m']) for a in assets])
    print('Photo localization',sum(r['localized'] for r in records), '/',len(records))

if __name__=='__main__':main()
