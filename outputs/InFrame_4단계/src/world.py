import math,json
from pathlib import Path
import numpy as np, habitat_sim as h, magnum as mn, quaternion
from habitat_sim.utils.common import quat_from_angle_axis
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from PIL import Image
from prepare import ROOT,STAGES,FIRE,WIDE,dump

W,H=192,144
DT=.25
def xz(p):return np.asarray(p)[...,[0,2]]
def hd(a,b):return float(np.linalg.norm(xz(b)-xz(a)))
def heading(a,b):
    d=np.asarray(b)-a;return math.atan2(-d[0],-d[2])
def wrap(a):return (a+math.pi)%(2*math.pi)-math.pi
def geo(pf,a,b):
    p=h.ShortestPath();p.requested_start=a;p.requested_end=b
    return float(p.geodesic_distance) if pf.find_path(p) else None
def driveable(pf,a,b):
    # A straight-line command may be blocked even when its two ends are on the same island.
    n=max(1,math.ceil(hd(a,b)/.08));cur=a
    for i in range(1,n+1):
        want=a+(b-a)*(i/n);cur=np.asarray(pf.try_step_no_sliding(cur,want))
        if not np.isfinite(cur).all() or hd(cur,want)>.0015:return False
    return abs(cur[1]-b[1])<.045
def normpose(p):return np.asarray(p,dtype=float)
class World:
    def __init__(self,name,register=True):
        self.name=name;wide=name=='castle';self.wide=wide
        cfg=h.SimulatorConfiguration();cfg.scene_id=str(WIDE/'castle.stage_config.json' if wide else FIRE/'fire.stage_config.json');cfg.allow_sliding=False
        ac=h.agent.AgentConfiguration();ac.radius=.22;ac.height=.65;ac.sensor_specifications=[]
        for uuid,typ in [('rgb',h.SensorType.COLOR),('depth',h.SensorType.DEPTH)]:
            c=h.CameraSensorSpec();c.uuid=uuid;c.sensor_type=typ;c.resolution=[H,W];c.position=mn.Vector3(0,.46,0);c.orientation=mn.Vector3(-.2,0,0);c.hfov=78;ac.sensor_specifications.append(c)
        self.sim=h.Simulator(h.Configuration(cfg,[ac]));self.pf=pf=self.sim.pathfinder
        assert pf.load_nav_mesh(str(WIDE/'castle.navmesh' if wide else FIRE/'fire.navmesh'))
        self.agent=self.sim.initialize_agent(0)
        if wide:
            meta=json.loads((WIDE/'registration.json').read_text());self.island=meta['floor_island'];self.anchor={'C':np.array(meta['anchor'])}
            self.support={'C':np.load(WIDE/'support.npz')['C']}
        else:
            meta=json.loads((FIRE/'alignment.json').read_text());self.anchor={k:np.array(v['sim_xyz_m']) for k,v in meta['assets'].items()};T=np.array(meta['map_to_sim'])
            old=np.load((FIRE/'map_support.npz') if (FIRE/'map_support.npz').exists() else STAGES/'InFrame_Fire_2단계/scene.npz');self.support={k:old['support_'+k]@T[:3,:3].T+T[:3,3] for k in self.anchor}
            saved=json.loads((FIRE/'simulation.json').read_text());self.island=saved['main_island'];self.trace=np.array(saved['targets']['A']['trace'])
        self.grid=[];self.refs={}
        if wide:self.build_graph()
        else:
            for k in self.anchor:self.refs[k]=[self.trace[-1]]
        if register:self.register()
        else:
            recorded=json.loads((ROOT/'calibration'/self.name/'views.json').read_text())
            for k, rr in self.refs.items():
                saved=[np.array(z['xyz']) for z in recorded['views'][k]]
                assert np.allclose(rr,saved,atol=1e-6)
                self.refs[k]=saved
    def reset(self,p,yaw):
        s=h.AgentState();s.position=p;s.rotation=quat_from_angle_axis(yaw,np.array([0.,1.,0.]));self.agent.set_state(s)
    def pose(self):
        s=self.agent.get_state();f=quaternion.as_rotation_matrix(s.rotation)@np.array([0.,0.,-1.])
        return np.asarray(s.position).copy(),math.atan2(-f[0],-f[2])
    def sensor(self,k):
        s=self.sim._sensors[k];s.draw_observation();return s.get_observation()
    def rgb(self):return np.ascontiguousarray(self.sensor('rgb')[:,:,:3])
    def visible(self):
        dep=self.sensor('depth');s=self.agent.get_state().sensor_states['depth'];rot=quaternion.as_rotation_matrix(s.rotation.inverse())
        f=W/2/math.tan(math.radians(39));out={}
        for k,points in self.support.items():
            a=(points-np.asarray(s.position))@rot.T;z=-a[:,2];uv=np.rint(np.c_[W/2+f*a[:,0]/np.maximum(z,.001),H/2-f*a[:,1]/np.maximum(z,.001)]).astype(int)
            ok=(z>.03)&(uv[:,0]>=0)&(uv[:,0]<W)&(uv[:,1]>=0)&(uv[:,1]<H)
            x,y=uv[ok].T;matched=np.abs(dep[y,x]-z[ok])<.035;x,y=x[matched],y[matched];n=len(np.unique(y*W+x))
            box=[int(x.min()),int(y.min()),int(x.max()),int(y.max())] if n else None
            out[k]=dict(pixels=n,box=box,visible=bool(n>=30 and box[2]-box[0]>=5 and box[3]-box[1]>=9))
        return out
    def build_graph(self):
        pf=self.pf;v=np.array(pf.build_navmesh_vertices(self.island));lo=xz(v).min(0);hi=xz(v).max(0);self.spacing=.24
        pts=[];ids={};rows=[];cols=[];vals=[]
        for ix,x in enumerate(np.arange(lo[0],hi[0],self.spacing)):
            for iz,z in enumerate(np.arange(lo[1],hi[1],self.spacing)):
                req=np.array([x,.04,z]);p=np.array(pf.snap_point(req,self.island))
                if not np.isfinite(p).all() or hd(p,req)>.002 or abs(p[1]-.04)>.25 or pf.distance_to_closest_obstacle(p)<.085:continue
                i=len(pts);ids[ix,iz]=i;pts.append(p)
                for dx,dz in [(-1,-1),(-1,0),(-1,1),(0,-1)]:
                    j=ids.get((ix+dx,iz+dz))
                    if j is None or not driveable(pf,p,pts[j]) or not driveable(pf,pts[j],p):continue
                    cost=np.linalg.norm(p-pts[j]);rows.extend([i,j]);cols.extend([j,i]);vals.extend([cost,cost])
        self.grid=pts=np.array(pts);mat=csr_matrix((vals,(rows,cols)),shape=(len(pts),len(pts)))
        # Register ground-level viewpoints near C with RGB and depth before selecting starts.
        t=self.anchor['C'];cand=np.flatnonzero((np.linalg.norm(xz(pts)-xz(t),axis=1)>.80)&(np.linalg.norm(xz(pts)-xz(t),axis=1)<1.20))
        chosen=[]
        for i in sorted(cand,key=lambda i:abs(hd(pts[i],t)-1.0)):
            if any(hd(pts[j],pts[i])<.70 for j in chosen):continue
            self.reset(pts[i],heading(pts[i],t));hit=self.visible()['C']
            if hit['pixels']>=160 and hit['box'][0]>0 and hit['box'][2]<W-1:chosen.append(i)
            if len(chosen)>=3:break
        if not chosen:raise RuntimeError('No optically verified viewpoint for C')
        self.refs={'C':[pts[i] for i in chosen]};self.refidx=chosen
        self.ds,self.pred=dijkstra(mat,directed=False,indices=chosen,return_predecessors=True)
    def register(self):
        d=ROOT/'calibration'/self.name;d.mkdir(parents=True,exist_ok=True);obj={}
        for k,rr in self.refs.items():
            obj[k]=[]
            for j,p in enumerate(rr):
                self.reset(p,heading(p,self.anchor[k]));hit=self.visible();assert hit[k]['visible']
                Image.fromarray(self.rgb()).save(d/f'{k}-{j}.jpg',quality=95)
                obj[k].append(dict(id=f'{k}-{j}',xyz=p.tolist(),visibility=hit))
        dump(d/'views.json',dict(island=self.island,connected_area_m2=self.pf.island_area(self.island),objects={k:v.tolist() for k,v in self.anchor.items()},views=obj))
        verts=np.array(self.pf.build_navmesh_vertices(self.island));indices=np.array(self.pf.build_navmesh_vertex_indices(self.island)).reshape(-1,3)
        np.savez_compressed(d/'floor.npz',v=verts,t=indices)
    def route(self,k,i):
        if self.wide:
            r=int(np.argmin(self.ds[:,i]));seq=[i]
            while seq[-1]!=self.refidx[r]:
                j=int(self.pred[r,seq[-1]]);assert j>=0;seq.append(j)
            pts=self.grid[seq]
        else:
            pts=self.trace[i:];r=0
        # String-pull only through verified free straight segments.
        path=[pts[0]];a=0
        while a<len(pts)-1:
            j=min(len(pts)-1,a+24)
            while j>a+1 and not driveable(self.pf,pts[a],pts[j]):j-=1
            path.append(pts[j]);a=j
        return np.asarray(path),r
    def close(self):self.sim.close()
