"""Build the registered, collision-aware public scene. Run from any directory."""
from pathlib import Path
import concurrent.futures, hashlib, json, urllib.request
import numpy as np, trimesh, habitat_sim as h
ROOT=Path(__file__).resolve().parents[1]
STAGES=ROOT.parent; FIRE=(ROOT/'scene/fire') if (ROOT/'scene/fire/fire.navmesh').exists() else STAGES/'InFrame_Fire_3단계'; CACHE=STAGES.parent/'work/teacher4'
WIDE=ROOT/'scene'; SHA='910c783fb954da8497ea5f811b843a76590ddddc'
def fetch(p,url,md5=None):
    p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():p.write_bytes(urllib.request.urlopen(url,timeout=120).read())
    if md5 and hashlib.md5(p.read_bytes()).hexdigest()!=md5:raise ValueError(p)
    return p
def dump(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def build():
    WIDE.mkdir(exist_ok=True)
    castle=fetch(CACHE/'castle/skokloster-castle.glb',f'https://huggingface.co/datasets/ai-habitat/habitat_test_scenes/resolve/{SHA}/skokloster-castle.glb')
    assert hashlib.sha256(castle.read_bytes()).hexdigest()=='b14e29e17f5e31d86a1002eefd77b7d345b265006481739ae480a847e6623f56'
    poly=json.loads(fetch(CACHE/'poly.json','https://api.polyhaven.com/files/korean_fire_extinguisher_01').read_text())['gltf']['1k']['gltf']
    parts=dict(poly['include'],**{'ext.gltf':poly})
    with concurrent.futures.ThreadPoolExecutor(6) as ex:list(ex.map(lambda kv:fetch(CACHE/'ext'/kv[0],kv[1]['url'],kv[1]['md5']),parts.items()))
    scene=trimesh.load(castle,force='scene')
    R=np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float)
    scene.apply_transform(R)
    # Vertical ray through the scanned floor. The nearest low floor face fixes the base.
    m=next(iter(scene.geometry.values()));n=scene.graph.nodes_geometry[0]
    verts=trimesh.transform_points(m.vertices,scene.graph[n][0]);tri=verts[m.faces]
    x,z=3.42,14.20;p=np.array([x,z]);uv=tri[:,:,[0,2]]
    ids=np.where(((uv.min(1)<=p)&(uv.max(1)>=p)).all(1))[0];uv=uv[ids]
    cand=[]
    for i,t in zip(ids,uv):
        try:u,v=np.linalg.solve((t[1:]-t[0]).T,p-t[0])
        except np.linalg.LinAlgError:continue
        if min(u,v,1-u-v)>=-1e-5:
            y=float(np.dot([1-u-v,u,v],tri[i,:,1]))
            if -.35<y<.35:cand.append(y)
    if not cand:raise RuntimeError('No scanned floor under the proposed fixture')
    base=np.array([x,max(cand),z]);ext=trimesh.load(CACHE/'ext/ext.gltf',force='scene')
    sup=[];np.random.seed(41)
    for i,n in enumerate(sorted(ext.graph.nodes_geometry)):
        t,key=ext.graph[n];g=ext.geometry[key].copy();g.apply_transform(t);g.apply_translation(base)
        # Baked scene shaded with captured colors, no external light required.
        scene.add_geometry(g,node_name='registered_C_'+str(i),geom_name='registered_C_'+str(i))
        sup.append(trimesh.sample.sample_surface(g,max(250,int(g.area*14500)))[0])
    mesh=WIDE/'castle-extinguisher.glb';scene.export(mesh)
    np.savez_compressed(WIDE/'support.npz',C=np.vstack(sup).astype('f4'))
    cfg=WIDE/'castle.stage_config.json';dump(cfg,dict(render_asset=mesh.name,collision_asset=mesh.name,up=[0,1,0],front=[0,0,-1],units_to_meters=1.0,requires_lighting=False))
    s=h.SimulatorConfiguration();s.scene_id=str(cfg);a=h.agent.AgentConfiguration();a.sensor_specifications=[]
    sim=h.Simulator(h.Configuration(s,[a]))
    try:
        settings=h.NavMeshSettings();settings.set_defaults();settings.agent_radius=.22;settings.agent_height=.65
        settings.agent_max_climb=.12;settings.cell_size=.04;settings.cell_height=.025
        assert sim.recompute_navmesh(sim.pathfinder,settings);assert sim.pathfinder.save_nav_mesh(str(WIDE/'castle.navmesh'))
        settings.write_to_json(str(WIDE/'nav_settings.json'));pf=sim.pathfinder;main=pf.get_island(pf.snap_point(np.array([x-1.,base[1],z])))
        dump(WIDE/'registration.json',dict(base=base.tolist(),anchor=(base+[0,.32,0]).tolist(),floor_island=int(main),area_m2=pf.island_area(main),total_area_m2=pf.navigable_area,
             geometry='public scanned castle + explicitly placed Poly Haven extinguisher C',source_sha256=hashlib.sha256(castle.read_bytes()).hexdigest(),model_manifest_md5={k:v['md5'] for k,v in parts.items()}))
    finally:sim.close()
if __name__=='__main__':build()
