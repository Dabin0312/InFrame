"""Fuse registered depth in estimated ORB-SLAM3 poses and plan on the observed grid."""
from pathlib import Path
import json, math, heapq, argparse
import numpy as np
from scipy.ndimage import distance_transform_edt, binary_closing, label
from scipy.spatial.transform import Rotation


def compact(file,data):
    file.write_text(json.dumps(data,separators=(',',':')))
def gridpath(free, start, cell_size):
    costs=np.full(free.shape,np.inf);costs[start]=0
    parent={};queue=[(0.,start)]
    while queue:
        score,at=heapq.heappop(queue)
        if score>costs[at]:continue
        r,c=at
        for dr,dc in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            dest=(r+dr,c+dc)
            if not (0<=dest[0]<free.shape[0] and 0<=dest[1]<free.shape[1] and free[dest]):continue
            if dr and dc and not(free[r+dr,c] and free[r,c+dc]):continue
            new=score+math.hypot(dc,dr)*cell_size
            if new+1e-9<costs[dest]:
                parent[dest]=at;costs[dest]=new;heapq.heappush(queue,(new,dest))
    return costs,parent
def segment(points):
    a,b=np.array(points[0]),np.array(points[-1])
    return np.rint(np.linspace(a,b,int(np.ceil(np.linalg.norm(a-b)*5))+1)).astype(int)
def derive(cloud,seed):
    res=.1
    low=np.floor(cloud[:,[0,2]].min(0)/res)*res-.3
    dims=np.ceil((cloud[:,[0,2]].max(0)+.3-low)/res).astype(int)
    cell=np.floor((cloud[:,[0,2]]-low)/res).astype(int)
    def raster(mask):
        grid=np.zeros(tuple(dims[::-1]),int)
        ij=cell[mask]
        np.add.at(grid,(ij[:,1],ij[:,0]),1)
        return grid
    def xy(rc):return low+(np.array(rc)[::-1]+.5)*res
    def rc(xy):return tuple(np.floor((xy-low)/res).astype(int)[::-1])
    walls=raster((cloud[:,1]>.12)&(cloud[:,1]<1.08))>=2
    floor=raster(np.abs(cloud[:,1])<.085)>0
    # Only close sampling gaps smaller than two cells; reject unknown and occupied neighbours.
    coverage=binary_closing(floor,structure=np.ones((3,3)))|floor
    clear=coverage & ~walls
    clearance=distance_transform_edt(clear)*res
    free=clearance>=.30
    # Grounded RGB-D red components. The wall sign is above the admitted height band.
    rgb=cloud[:,3:].astype(float)
    red=(rgb[:,0]>120)&(rgb[:,0]>rgb[:,1]*1.55)&(rgb[:,0]>rgb[:,2]*1.45)&(cloud[:,1]>.08)&(cloud[:,1]<.74)
    blobs,n=label(raster(red)>0,structure=np.ones((3,3)))
    scores=[]
    for label_id in range(1,n+1):
        sel=red & (blobs[cell[:,1],cell[:,0]]==label_id)
        if sel.sum()>15 and np.ptp(cloud[sel,1])>.32:
            scores.append((sel.sum(),label_id))
    if not scores:raise ValueError('No observed target')
    target_mask=red & (blobs[cell[:,1],cell[:,0]]==max(scores)[1])
    goal=np.median(cloud[target_mask,:3],axis=0)
    # The straight sections of the red cylinder constrain its centre even from a partial arc.
    band=cloud[target_mask & (cloud[:,1]>.20) & (cloud[:,1]<.58)][:,[0,2]]
    design=np.column_stack((2*band,np.ones(len(band))))
    fit=np.linalg.lstsq(design,np.sum(band**2,axis=1),rcond=None)[0]
    if np.linalg.norm(fit[:2]-goal[[0,2]])<.24:
        goal[[0,2]]=fit[:2]
    free_cells=np.argwhere(free)
    start=tuple(min(free_cells,key=lambda at:np.linalg.norm(xy(at)-seed)))
    costs,parents=gridpath(free,start,res)
    end_candidates=[]
    gr=rc(goal[[0,2]])
    for row,col in np.argwhere(np.isfinite(costs)):
        at=(row,col);dist=np.linalg.norm(xy(at)-goal[[0,2]])
        if .66<=dist<=.78:
            sight=segment((at,gr))
            away=np.linalg.norm(sight-np.array(gr),axis=1)*res>.26
            if not np.any(walls[sight[away,0],sight[away,1]]):end_candidates.append((costs[at],at))
    if not end_candidates:raise ValueError('No reachable viewpoint')
    end=min(end_candidates)[1]
    path=[end]
    while path[-1]!=start:path.append(parents[path[-1]])
    path.reverse();short=[start];i=0
    while i<len(path)-1:
        for j in range(len(path)-1,i,-1):
            check=segment((path[i],path[j]))
            if np.all(free[check[:,0],check[:,1]]):break
        short.append(path[j]);i=j
    route=np.array([xy(a) for a in short]).round(4)
    checked=np.concatenate([segment((a,b)) for a,b in zip(short,short[1:])])
    assert free[checked[:,0],checked[:,1]].all()
    occupancy=np.where(walls,'#',np.where(free,'.',np.where(coverage,':',' ')))
    return dict(origin=np.round(low,4).tolist(),resolution=res,rows=[''.join(r) for r in occupancy],
                target=goal.round(4).tolist(),route=route.tolist(),
                pathLength=round(float(np.linalg.norm(np.diff(route,axis=0),axis=1).sum()),4),
                clearance=round(float(clearance[checked[:,0],checked[:,1]].min()),3)),target_mask
def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('--input',type=Path,default=Path(__file__).with_name('observations.npz'))
    args.add_argument('--out',type=Path,required=True)
    args=args.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    evidence=np.load(args.input,allow_pickle=False)
    initial=evidence['initial'];traj=evidence['trajectory'];truth_xyz=evidence['validation_positions']
    uvd=evidence['uvd'];rgb=evidence['rgb'];ends=evidence['ends'];starts=np.r_[0,ends[:-1]]
    ranges={int(f):slice(a,b) for f,a,b in zip(evidence['frame_ids'],starts,ends)}
    fx=192/math.tan(math.radians(35))
    points=[];colors=[];frames=[];seen=set();errors=[];counts=[]
    for row in traj:
        i=round((row[0]-1)*24)
        pose=initial.copy();pose[:3,:3]=initial[:3,:3]@Rotation.from_quat(row[4:]).as_matrix()
        pose[:3,3]=initial[:3,:3]@row[1:4]+initial[:3,3]
        # Renderer poses are used here only to *measure* tracking error.
        errors.append(np.linalg.norm(truth_xyz[i]-pose[:3,3]))
        if i in ranges:
            sl=ranges[i];x,y,mm=uvd[sl].T
            good=(mm>100)&(mm<10000)
            xx=x[good];yy=y[good];z=mm[good]*.001
            frame_rgb=rgb[sl][good]
            cam=np.stack(((xx-255.5)*z/fx,(yy-191.5)*z/fx,z),axis=1)
            xyz=cam@pose[:3,:3].T+pose[:3,3]
            # Clip ceiling points only for the cutaway map; robot occupancy uses lower geometry.
            keep=np.flatnonzero((xyz[:,1]<2.62)&(xyz[:,1]>-.12))
            for n in keep:
                key=tuple(np.floor(xyz[n]/.034).astype(int))
                if key in seen:continue
                seen.add(key);points.append(xyz[n]);colors.append(frame_rgb[n])
        counts.append(len(seen))
        frames.append([round(i/24,3),*np.round(pose[:3,3],4),*np.round(Rotation.from_matrix(pose[:3,:3]).as_quat(),5),len(seen)])
    assert len(traj)==len(truth_xyz),'Unexpected loss of tracking'
    color=np.asarray(colors);pts=np.asarray(points);cloud=np.column_stack((pts,color))
    # Robot deployment seed comes from the first estimated view, one metre into the surveyed floor.
    seed=initial[:3,3][[0,2]]+initial[:3,2][[0,2]]*1.05
    nav,mask=derive(cloud,seed)
    sparse=evidence['landmarks']@initial[:3,:3].T+initial[:3,3]
    dtype=np.dtype([('p','<i2',3),('rgb','u1',3),('goal','u1')])
    binary=np.zeros(len(pts),dtype=dtype);binary['p']=np.rint(pts*1000);binary['rgb']=color;binary['goal']=mask
    binary.tofile(out/'surface.bin')
    first=next(i for i,n in enumerate(counts) if np.count_nonzero(mask[:n])>=8)
    nav.update(scene='workshop-rgbd-01',frameCount=len(traj),landmarks=len(sparse),surfacePoints=len(pts),
               targetFirstFrame=first,observedTargetPoints=int(mask.sum()),radius=.22,
               trackingRMSE=round(float(np.mean(np.square(errors))**.5),4))
    compact(out/'scan.json',dict(scene=nav['scene'],fps=len(frames)/12,frames=frames,sparse=sparse.round(3).tolist()))
    (out/'episode.js').write_text('export const episode = '+json.dumps(nav,separators=(',',':'))+';\n')

    print({k:v for k,v in nav.items() if k!='rows'})
if __name__=='__main__':main()
