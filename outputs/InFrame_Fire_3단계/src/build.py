"""Export exactly the stage-2 Fire samples and anchors, with observed floor support."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.ndimage import label

BASE=Path(__file__).resolve().parents[2]/'InFrame_Fire_2단계'
sys.path.insert(0,str(BASE/'src'))
from geometry import lift, dump
CELL=.025
KEYS=range(0,80,10)
HOLDOUT=[5,25,45,65]
RADIUS=.22
HEIGHT=.65

def transform(x,T):
    return np.einsum('ij,nj->ni',T[:3,:3],x)+T[:3,3]

def floor_frame(points):
    # Sample real planes; reject walls and surfaces above the floor.
    rng=np.random.default_rng(14);pts=points[rng.choice(len(points),4500,replace=False)].astype(float)
    best=0
    for _ in range(1400):
        a,b,c=pts[rng.choice(len(pts),3,replace=False)]
        n=np.cross(b-a,c-a);norm=np.linalg.norm(n)
        if norm<1e-5:continue
        n/=norm
        if n[1]<0:n=-n
        d=n@a
        if n[1]<.72 or not .6<d<2:continue
        count=(np.abs(np.einsum('ij,j->i',pts,n)-d)<.017).sum()
        if count>best:best=count;best_plane=(n.copy(),d)
    n,d=best_plane
    for _ in range(3):
        m=np.abs(np.einsum('ij,j->i',points,n)-d)<.019
        center=points[m].mean(0,dtype=float)
        _,_,vh=np.linalg.svd(points[m]-center,full_matrices=False);n=vh[-1]
        if n[1]<0:n=-n
        d=n@center
    up=-n
    right=np.array([1.,0.,0.]);right-=up*(right@up);right/=np.linalg.norm(right)
    back=np.cross(right,up)
    T=np.eye(4);T[:3,:3]=np.stack((right,up,back));T[:3,3]=[0,d,0]
    return T,dict(plane_inliers=int(m.sum()),points=int(len(points)),median_plane_residual_m=float(np.median(np.abs(np.einsum('ij,j->i',points[m],n)-d))),camera_height_m=float(d))

def glb(path,verts,faces,colors):
    v=np.asarray(verts,dtype='<f4');faces=np.asarray(faces,dtype='<u4').reshape(-1);colors=np.asarray(colors,dtype='uint8')
    if colors.shape[1]==3:colors=np.c_[colors,np.full(len(v),255,dtype=np.uint8)]
    bins=bytearray();views=[];acc=[]
    for raw,component,kind,count,target in [(v,5126,'VEC3',len(v),34962),(colors,5121,'VEC4',len(v),34962),(faces,5125,'SCALAR',len(faces),34963)]:
        data=raw.tobytes();views.append(dict(buffer=0,byteOffset=len(bins),byteLength=len(data),target=target))
        a=dict(bufferView=len(views)-1,componentType=component,type=kind,count=count)
        if kind=='VEC3':a.update(min=v.min(0).tolist(),max=v.max(0).tolist())
        if kind=='VEC4':a['normalized']=True
        acc.append(a);bins.extend(data);bins.extend(b'\0'*(-len(bins)%4))
    data=dict(asset={'version':'2.0'},scene=0,scenes=[{'nodes':[0]}],nodes=[{'mesh':0}],meshes=[{'primitives':[{'attributes':{'POSITION':0,'COLOR_0':1},'indices':2,'material':0}]}],
       materials=[{'name':'RGB-D','doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1}}],buffers=[{'byteLength':len(bins)}],bufferViews=views,accessors=acc)
    header=json.dumps(data,separators=(',',':')).encode();header+=b' '*(-len(header)%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(header)+len(bins))+struct.pack('<I4s',len(header),b'JSON')+header+struct.pack('<I4s',len(bins),b'BIN\0')+bins)

def patch(scene,i,pose,K,T):
    stem=scene/'seq-01'/f'frame-{i:06}'
    depth=cv2.imread(str(stem.with_suffix('.depth.png')),-1)[::6,::6]/1000
    color=cv2.imread(str(stem.with_suffix('.color.png')))[::6,::6,::-1]
    valid=(depth>.15)&(depth<6)
    v,u=np.where(valid)
    raw=lift(np.c_[u*6,v*6],depth[v,u],pose,K)
    points=transform(raw,T);ids=np.full(depth.shape,-1);ids[v,u]=np.arange(len(v))
    tl=ids[:-1,:-1].ravel();tr=ids[:-1,1:].ravel();bl=ids[1:,:-1].ravel();br=ids[1:,1:].ravel()
    triangles=np.concatenate((np.c_[tl,bl,tr],np.c_[tr,bl,br]));triangles=triangles[(triangles>=0).all(1)]
    q=points[triangles];width=np.max(np.linalg.norm(q-np.roll(q,1,axis=1),axis=2),axis=1)
    return raw,points,color[valid],triangles[width<.085]

def grid_votes(points,triangles,origin,shape):
    # Rasterize only triangles with measured floor beneath all vertices.
    coords=(points[:,[0,2]]-origin)/CELL
    floor=np.zeros(shape,np.uint8);obs=np.zeros(shape,np.uint8)
    ground=triangles[np.max(np.abs(points[triangles,1]),axis=1)<.035]
    # Rasterize at higher resolution, sampling the cell center rather than any touching corner.
    large=np.zeros((shape[0]*4,shape[1]*4),np.uint8)
    for poly in np.int32(np.rint(coords[ground]*4)):cv2.fillConvexPoly(large,poly,1)
    floor=large[2::4,2::4].copy()
    object_points=(points[:,1]>.045)&(points[:,1]<HEIGHT+.015)
    xy=np.floor(coords[object_points]).astype(int);heights=points[object_points,1]
    valid=(xy[:,0]>=0)&(xy[:,0]<shape[1])&(xy[:,1]>=0)&(xy[:,1]<shape[0])
    x,z=xy[valid].T;obs[z,x]=1
    top=np.zeros(shape);np.maximum.at(top,(z,x),heights[valid])
    return floor,obs,top

def grid_mesh(g,origin,top=None):
    rows,cols=np.where(g);quads=[];colors=[];idx=[]
    for r,c in zip(rows,cols):
        x,z=origin+np.array([c,r])*CELL
        vs=np.array([[x,0,z],[x,0,z+CELL],[x+CELL,0,z+CELL],[x+CELL,0,z]])
        faces=[[0,1,2],[0,2,3]]
        color=[170,175,168]
        if top is not None:
            vs=np.vstack((vs,vs+[0,max(.05,top[r,c]),0]))
            faces=[[4,5,6],[4,6,7],[0,4,7],[0,7,3],[1,5,4],[1,4,0],[2,6,5],[2,5,1],[3,7,6],[3,6,2]]
            color=[127,96,68]
        offset=len(colors);quads.append(vs);colors.extend([color]*len(vs));idx.extend((np.array(faces)+offset).tolist())
    return np.concatenate(quads),np.array(idx),np.array(colors)

def main():
    p=argparse.ArgumentParser();p.add_argument('scene',type=Path);p.add_argument('out',type=Path);a=p.parse_args();out=a.out;out.mkdir(exist_ok=True,parents=True)
    src=np.load(BASE/'scene.npz');m=json.loads((BASE/'map.json').read_text());K=np.array(m['K'])
    T,plane=floor_frame(src['xyz']);poses={}
    for ts,x,y,z,*q in np.loadtxt(BASE/'src/CameraTrajectory.txt'):
        P=np.eye(4);P[:3,:3]=Rotation.from_quat(q).as_matrix();P[:3,3]=[x,y,z];poses[round((ts-1)*30)]=P
    points=transform(src['xyz'],T);xz=points[:,[0,2]]
    origin=np.floor(xz.min(0)/CELL)*CELL-.5
    shape=tuple(np.ceil((xz.max(0)+.5-origin)/CELL).astype(int)[::-1])
    votes={};heights=np.zeros(shape);total=0;faces=[];rgb=[];raw=[]
    for key,ids in [('map',KEYS),('heldout',HOLDOUT)]:
        f=np.zeros(shape,int);b=f.copy()
        for i in ids:
            raw_pts,v,colors,tris=patch(a.scene,i,poses[i],K,T)
            floor,obs,top=grid_votes(v,tris,origin,shape);f+=floor;b+=obs
            if key=='map':
                heights=np.maximum(heights,top);faces.append(tris+total);total+=len(v);rgb.append(colors);raw.append(raw_pts)
        votes[key+'_floor']=f;votes[key+'_obs']=b
    delta=np.max(np.abs(np.concatenate(raw)-src['xyz']))
    assert delta<1e-5 and np.array_equal(np.concatenate(rgb),src['rgb'])
    glb(out/'fire.glb',points,np.concatenate(faces),src['rgb'])
    occupied=votes['map_obs']>=2
    supported=votes['map_floor']>=2
    free=supported & ~occupied
    f,fi,fc=grid_mesh(free,origin);o,oi,oc=grid_mesh(occupied,origin,heights)
    glb(out/'floor.glb',f,fi,fc);glb(out/'collision.glb',np.r_[f,o],np.r_[fi,oi+len(f)],np.r_[fc,oc])
    for name,render,coll in [('fire','fire.glb','collision.glb'),('floor','floor.glb','floor.glb')]:
        dump(out/(name+'.stage_config.json'),dict(render_asset=render,collision_asset=coll,up=[0,1,0],front=[0,0,-1],scale=[1,1,1],units_to_meters=1.0,requires_lighting=False))
    grid=np.where(occupied,2,np.where(free,1,0)).astype('uint8')
    np.savez_compressed(out/'observations.npz',grid=grid,origin=origin,cell=CELL,heights=heights,**votes)
    asset={}
    for ob in m['objects']:
        xyz=np.array(ob['surface_anchor_xyz_m']);sim=transform(xyz[None],T)[0]
        asset[ob['id']]={'map_xyz_m':xyz.tolist(),'sim_xyz_m':sim.tolist(),'roundtrip_error_m':float(np.linalg.norm(transform(sim[None],np.linalg.inv(T))[0]-xyz))}
    report=dict(map_to_sim=T.tolist(),sim_to_map=np.linalg.inv(T).tolist(),plane=plane,assets=asset,map_sha256=hashlib.sha256((BASE/'map.json').read_bytes()).hexdigest(),pointcloud_sha256=hashlib.sha256((BASE/'scene.npz').read_bytes()).hexdigest(),geometry_points=len(points),triangles=sum(map(len,faces)),max_vertex_delta_m=float(delta),registration_frames=list(KEYS),heldout_geometry_frames=HOLDOUT,grid_counts={'open_floor':int(free.sum()),'observed_blocker':int(occupied.sum())},cell_m=CELL)
    dump(out/'alignment.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
