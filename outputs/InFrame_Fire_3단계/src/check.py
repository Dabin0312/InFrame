"""Check the robot's swept footprint at 2 mm intervals against measured cell boundaries."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
def main(out):
    alignment=json.loads((out/'alignment.json').read_text());sim=json.loads((out/'simulation.json').read_text());g=np.load(out/'observations.npz')
    frozen=out.parent/'InFrame_Fire_2단계';original=json.loads((frozen/'map.json').read_text())
    assert hashlib.sha256((frozen/'scene.npz').read_bytes()).hexdigest()==alignment['pointcloud_sha256']
    assert hashlib.sha256((frozen/'map.json').read_bytes()).hexdigest()==alignment['map_sha256']
    for a in original['objects']:assert a['surface_anchor_xyz_m']==alignment['assets'][a['id']]['map_xyz_m']
    trace=np.array(sim['targets']['A']['trace'])[:,[0,2]]
    dense=np.concatenate([np.linspace(x,y,max(2,int(np.ceil(np.linalg.norm(x-y)/.002))+1)) for x,y in zip(trace,trace[1:])])
    areas={'mapped_obstacle':g['grid']==2,'mapped_unknown':g['grid']==0,'heldout_obstacle':g['heldout_obs']>=1,'heldout_unknown':(g['heldout_floor']==0)&(g['heldout_obs']==0)}
    clearance={}
    for name,mask in areas.items():
        z,x=np.where(mask);pts=(np.c_[x,z]+.5)*g['cell']+g['origin']
        ds=[]
        for q in np.array_split(dense,16):
            delta=np.maximum(np.abs(q[:,None,:]-pts[None,:,:])-g['cell']/2,0)
            ds.extend(np.sqrt((delta**2).sum(-1)).min(1))
        clearance[name]=float(min(ds))
    result=dict(min_clearance_center_to_cell_edge_m=clearance,sample_spacing_at_most_m=.002,body_radius_m=sim['robot_radius_m'],checked_positions=len(dense),targets_arrived={k:v['arrived'] for k,v in sim['targets'].items()},anchor_roundtrip_max_m=max(i['roundtrip_error_m'] for i in alignment['assets'].values()),cases={p['id']:{'data':p['independent_depth_reference'],'sim':p['engine_outcome']} for p in sim['probes']})
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert all(result['targets_arrived'].values())
    assert min(clearance['mapped_obstacle'],clearance['mapped_unknown'])>=sim['robot_radius_m']
    print(result)
if __name__=='__main__':main(Path(sys.argv[1]))
