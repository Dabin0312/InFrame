"""Rebuild Habitat's navmesh, drive a fixed-size agent and replay collision probes."""
import argparse,json,math
from pathlib import Path
import habitat_sim as h
import magnum as mn
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
from habitat_sim.utils.common import quat_from_angle_axis

RADIUS=.22
HEIGHT=.65
GRID_ALLOWANCE=.025/(2**.5)
STEP=.01
Y=.01

def simulator(stage,sensors=False):
    cfg=h.SimulatorConfiguration();cfg.scene_id=str(stage.resolve());cfg.allow_sliding=False
    agent=h.agent.AgentConfiguration();agent.radius=RADIUS;agent.height=HEIGHT
    agent.sensor_specifications=[]
    if sensors:
        for name,kind in [('rgb',h.SensorType.COLOR),('depth',h.SensorType.DEPTH)]:
            s=h.CameraSensorSpec();s.uuid=name;s.sensor_type=kind;s.resolution=[480,640]
            s.position=mn.Vector3(0,.46,0);s.orientation=mn.Vector3(-.20,0,0);s.hfov=78
            agent.sensor_specifications.append(s)
    return h.Simulator(h.Configuration(cfg,[agent]))

def build_nav(out):
    sim=simulator(out/'floor.stage_config.json')
    try:
        n=h.NavMeshSettings();n.set_defaults();n.cell_size=.005;n.cell_height=.01
        n.agent_radius=RADIUS+GRID_ALLOWANCE;n.agent_height=HEIGHT;n.agent_max_climb=.02;n.region_min_size=1;n.region_merge_size=2;n.edge_max_error=.15
        if not sim.recompute_navmesh(sim.pathfinder,n):raise RuntimeError('NavMesh failed')
        sim.pathfinder.save_nav_mesh(str(out/'fire.navmesh'));n.write_to_json(str(out/'nav_settings.json'))
    finally:sim.close()

def state_at(agent,point,look):
    d=look-point;yaw=-math.atan2(d[0],-d[2])
    state=h.AgentState();state.position=point;state.rotation=quat_from_angle_axis(yaw,np.array([0.,1.,0.]));agent.set_state(state)

def drive(agent,waypoints,capture=None):
    points=[p.copy() for p in waypoints];state_at(agent,points[0],points[1])
    trace=[np.asarray(agent.get_state().position).copy()]
    halted=False
    for end in points[1:]:
        current=trace[-1]
        if np.linalg.norm(end-current)<.001:continue
        state_at(agent,current,end)
        if capture is not None:capture(current)
        # Forward steps go through Habitat's agent controls and its NavMesh move filter.
        for _ in range(int(math.ceil(np.linalg.norm(end-current)/STEP))+3):
            remaining=np.linalg.norm(end-trace[-1])
            if remaining<.001:break
            ask=min(remaining,STEP);agent.agent_config.action_space['move_forward'].actuation.amount=float(ask)
            reported=agent.act('move_forward')
            after=np.asarray(agent.get_state().position).copy();dist=np.linalg.norm(after-trace[-1]);trace.append(after)
            if capture is not None and len(trace)%2==0:capture(after)
            if dist<ask-.001:
                halted=True;break
        if halted:break
    return np.array(trace),halted

def route(pf,start,goal):
    path=h.ShortestPath();path.requested_start=start;path.requested_end=goal;found=pf.find_path(path)
    return ([np.array(v) for v in path.points],float(path.geodesic_distance)) if found else ([],None)

def interior_route(pf,island,start,goal,clearance):
    # Search a fine lattice of feasible centers, verifying each move with Habitat.
    import heapq
    verts=np.asarray(pf.build_navmesh_vertices(island))
    lo=verts[:,[0,2]].min(0);hi=verts[:,[0,2]].max(0);spacing=.00625
    positions=[]
    for x in np.arange(lo[0]+spacing*.48,hi[0],spacing):
        for z in np.arange(lo[1]+spacing*.48,hi[1],spacing):
            pos=np.array([x,Y,z])
            if pf.is_navigable(pos) and pf.get_island(pos)==island and np.linalg.norm(np.asarray(pf.snap_point(pos,island))-pos)<.0002:positions.append(pos)
    pts=np.array([start,goal]+positions)
    tree=cKDTree(pts[:,[0,2]])
    def can_follow(a,b):
        delta=b-a;length=np.linalg.norm(delta);steps=max(1,int(math.ceil(length/STEP)))
        cur=a.copy()
        for i in range(1,steps+1):
            want=a+delta*(i/steps);cur=np.asarray(pf.try_step_no_sliding(cur,want))
            if np.linalg.norm(cur-want)>.0002:return False
        return True
    measure=clearance(pts)
    parent={};best={0:0.};queue=[(0.,0.,0)]
    while queue:
        _,cost,i=heapq.heappop(queue)
        if i==1:break
        if cost>best[i]:continue
        for j in tree.query_ball_point(pts[i,[0,2]],spacing*1.5):
            extra=max(0,min(measure[i],measure[j])-RADIUS)
            proposed=cost+np.linalg.norm(pts[j]-pts[i])*(1+.025/(.004+extra))
            if proposed>=best.get(j,float('inf')) or not can_follow(pts[i],pts[j]):continue
            best[j]=proposed;parent[j]=i
            heapq.heappush(queue,(proposed+np.linalg.norm(pts[j]-goal),proposed,j))
    if 1 not in parent:return []
    path=[1]
    while path[-1]!=0:path.append(parent[path[-1]])
    path=path[::-1];smooth=[pts[path[0]]];i=0
    while i<len(path)-1:
        j=len(path)-1
        while j>i+1:
            a,b=pts[path[i]],pts[path[j]]
            samples=np.linspace(a,b,max(2,int(np.ceil(np.linalg.norm(b-a)/.004))+1))
            if clearance(samples).min()>=min(measure[path[i:j+1]])-.0005 and can_follow(a,b):break
            j-=1
        smooth.append(pts[path[j]]);i=j
    return smooth

def make_tree(g,origin,cell):
    z,x=np.where(g);pts=origin+(np.c_[x,z]+.5)*cell
    return cKDTree(pts)

def screenshot(sim,agent,position,assets,dest,support):
    target=np.mean(list(assets.values()),axis=0);state_at(agent,position,target)
    obs=sim.get_sensor_observations();im=Image.fromarray(obs['rgb'][:,:,:3]);im.save(dest)
    sensor=agent.get_state().sensor_states['depth'];s=sensor.rotation;inv=s.inverse()
    import quaternion
    rot=quaternion.as_rotation_matrix(inv)
    depth=obs['depth'];H,W=depth.shape;f=W/2/math.tan(math.radians(78)/2)
    verified={}
    for k,world in support.items():
        cam=np.einsum('ij,nj->ni',rot,world-np.asarray(sensor.position));z=-cam[:,2]
        uv=np.rint(np.c_[W/2+f*cam[:,0]/np.maximum(z,.0001),H/2-f*cam[:,1]/np.maximum(z,.0001)]).astype(int)
        ok=(z>0)&(uv[:,0]>=0)&(uv[:,0]<W)&(uv[:,1]>=0)&(uv[:,1]<H)
        x,y=uv[ok].T;depth_ok=np.abs(depth[y,x]-z[ok])<.035
        verified[k]=dict(median_visible_xy=np.median(np.c_[x[depth_ok],y[depth_ok]],axis=0).tolist() if depth_ok.any() else None,projected_samples=int(ok.sum()),depth_agreeing_samples=int(depth_ok.sum()),distinct_depth_agreeing_pixels=len(np.unique(y[depth_ok]*W+x[depth_ok])))
    return verified

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();out=a.out.resolve()
    build_nav(out);sim=simulator(out/'fire.stage_config.json',True)
    try:
        pf=sim.pathfinder
        if not pf.load_nav_mesh(str(out/'fire.navmesh')):raise RuntimeError('Navmesh reload failed')
        grid=np.load(out/'observations.npz');g=grid['grid'];origin=grid['origin'];cell=float(grid['cell'])
        locs=[];cells=[];main=max(range(pf.num_islands),key=pf.island_area)
        for z,x in zip(*np.where(g==1)):
            wx,wz=origin+(np.array([x,z])+.5)*cell;point=np.array([wx,Y,wz])
            if (pf.is_navigable(point) and pf.get_island(point)==main and
                    np.linalg.norm(np.asarray(pf.snap_point(point,main))-point)<.0002 and pf.distance_to_closest_obstacle(point)>.005):
                locs.append(point);cells.append((z,x))
        locs=np.array(locs);meta=json.loads((out/'alignment.json').read_text());assets={k:np.array(v['sim_xyz_m']) for k,v in meta['assets'].items()}
        old=np.load(out.parent/'InFrame_Fire_2단계/scene.npz');T=np.array(meta['map_to_sim'])
        support={k:np.einsum('ij,nj->ni',T[:3,:3],old['support_'+k])+T[:3,3] for k in assets}
        xz=locs[:,[0,2]];targets=np.mean(list(assets.values()),axis=0)[[0,2]]
        start=locs[np.argmax(np.linalg.norm(xz-targets,axis=1))]
        observed_clearance=distance_transform_edt(g==1)*cell
        probe_start=locs[np.argmax([observed_clearance[i] for i in cells])]
        edges=make_tree(g!=1,origin,cell)
        def clearance(points):
            centers=np.atleast_2d(points)[:,[0,2]];_,near=edges.query(centers,k=9)
            delta=np.maximum(np.abs(edges.data[near]-centers[:,None,:])-cell/2,0)
            return np.linalg.norm(delta,axis=2).min(1)
        agent=sim.initialize_agent(0);navigation={}
        for k,t in assets.items():
            goal=locs[np.argmin(np.linalg.norm(xz-t[[0,2]],axis=1))]
            wp,length=route(pf,start,goal)
            if not wp:raise RuntimeError('Unreachable goal on same island')
            short_trace,short_blocked=drive(agent,wp)
            executed=interior_route(pf,main,start,goal,clearance) or wp
            frames=[];camera_trace=[]
            def capture(point):
                frames.append(np.asarray(Image.fromarray(sim.get_sensor_observations()['rgb'][:,:,:3]).resize((384,288),Image.Resampling.LANCZOS)));camera_trace.append(point.copy())
            trace,blocked=drive(agent,executed,capture if k=='A' else None);arrived=np.linalg.norm(trace[-1]-goal)<.012
            closest=np.asarray(pf.snap_point(np.array([t[0],Y,t[2]]),main))
            vis=screenshot(sim,agent,trace[-1],assets,out/('approach_'+k+'.png'),support)
            if k=='A':
                capture(trace[-1]);np.savez_compressed(out/'camera_trace.npz',rgb=np.array(frames),xyz=np.array(camera_trace))
            navigation[k]=dict(start=start.tolist(),goal=goal.tolist(),actual=trace[-1].tolist(),arrived=bool(arrived),
                halted=blocked,requested_geodesic_m=length,driven_m=float(np.linalg.norm(np.diff(trace,axis=0),axis=1).sum()),
                footprint_to_anchor_centerline_horizontal_m=float(np.linalg.norm(trace[-1,[0,2]]-t[[0,2]])),
                closest_navmesh_horizontal_m=float(np.linalg.norm(closest[[0,2]]-t[[0,2]])),
                trace=trace.tolist(),waypoints=[q.tolist() for q in executed],shortest_waypoints=[q.tolist() for q in wp],
                shortest_replay=dict(halted=short_blocked,endpoint=short_trace[-1].tolist(),driven_m=float(np.linalg.norm(np.diff(short_trace,axis=0),axis=1).sum())),depth_visibility=vis)
        ref_obs=make_tree(grid['heldout_obs']>=1,origin,cell)
        ref_unknown=make_tree((grid['heldout_floor']==0)&(grid['heldout_obs']==0),origin,cell)
        map_obs=make_tree(g==2,origin,cell);map_unknown=make_tree(g==0,origin,cell)
        probes=[]
        # Fixed test rays on the same observed patch; the four held-out views never entered the mesh.
        for label,deg,length,expect in [('P1',0,.04,'pass'),('P2',220,.04,'pass'),('P3',300,.15,'pass'),
                ('C1',0,.45,'obstacle'),('C2',220,.45,'obstacle'),('C3',260,.45,'obstacle'),('U1',100,.55,'unknown')]:
            direction=np.array([math.cos(math.radians(deg)),0,math.sin(math.radians(deg))]);goal=probe_start+direction*length
            trace,halted=drive(agent,[probe_start,goal]);pos=trace[-1];xz=pos[[0,2]]
            dist,idx=map_obs.query(xz)
            # Record independent obstacle/floor support along the intended swept disk.
            desired=np.linspace(probe_start,goal,int(math.ceil(length/.005))+1)[:,[0,2]]
            hd=ref_obs.query(desired)[0];mu=ref_unknown.query(desired)[0]
            physical=np.flatnonzero(hd<=RADIUS);unknown=np.flatnonzero(mu<=RADIUS)
            po=int(physical[0]) if len(physical) else len(hd);un=int(unknown[0]) if len(unknown) else len(hd)
            ref='pass' if min(po,un)==len(hd) else ('obstacle' if po<un else 'unknown')
            near_obs=float(dist);near_unknown=float(map_unknown.query(xz)[0])
            actual='pass' if np.linalg.norm(pos-goal)<.003 else ('obstacle' if near_obs<near_unknown else 'unknown')
            probes.append(dict(id=label,expected=expect,independent_depth_reference=ref,engine_outcome=actual,
                requested=goal.tolist(),start=probe_start.tolist(),actual_endpoint=pos.tolist(),request_m=length,
                traveled_m=float(np.linalg.norm(np.diff(trace,axis=0),axis=1).sum()),halted=halted,trace=trace.tolist(),
                nearest_obstacle_xz=map_obs.data[idx].tolist(),map_obstacle_at_stop_m=near_obs,map_unknown_at_stop_m=near_unknown,
                heldout_obstacle_at_stop_m=float(ref_obs.query(xz)[0]),heldout_unknown_at_stop_m=float(ref_unknown.query(xz)[0])))
        islands=[]
        for idx in range(pf.num_islands):
            verts=np.array(pf.build_navmesh_vertices(idx));indices=np.array(pf.build_navmesh_vertex_indices(idx),dtype=int).reshape(-1,3)
            islands.append(dict(id=idx,area_m2=pf.island_area(idx),vertices=verts.tolist(),triangles=indices.tolist()))
        island_checks=[]
        for item in islands:
            tris=np.array(item['vertices'])[np.array(item['triangles'])]
            center=tris[0].mean(0);wp,dist=route(pf,start,center)
            island_checks.append(dict(id=item['id'],from_start_found=bool(wp),distance_m=dist,point=center.tolist()))
        r=dict(engine='Habitat-Sim',version=getattr(h,'__version__','0.3.3'),robot_radius_m=RADIUS,robot_height_m=HEIGHT,planning_margin_m=GRID_ALLOWANCE,
            robot_eye_height_m=.46,step_m=STEP,main_island=main,total_area_m2=pf.navigable_area,connected_area_m2=pf.island_area(main),
            islands=islands,island_tests=island_checks,targets=navigation,probes=probes)
        (out/'simulation.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
        print('Areas',[(it['id'],it['area_m2']) for it in islands],island_checks)
        for k,v in navigation.items():print(k,{key:val for key,val in v.items() if key not in ['trace','waypoints']})
        for v in probes:print(v['id'],v['independent_depth_reference'],v['engine_outcome'],v['traveled_m'])
    finally:sim.close()
if __name__=='__main__':main()
