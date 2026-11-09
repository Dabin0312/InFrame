"""Freeze the exact Stage 2/3 Fire inputs used here; no remapping or rescaling."""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from prepare import ROOT,STAGES,dump
def main():
    src=STAGES/'InFrame_Fire_3단계';dest=ROOT/'scene/fire';dest.mkdir(parents=True,exist_ok=True)
    files=['fire.stage_config.json','fire.glb','collision.glb','fire.navmesh','simulation.json','alignment.json']
    sha={}
    for name in files:
        shutil.copyfile(src/name,dest/name);sha[name]=hashlib.sha256((dest/name).read_bytes()).hexdigest()
    source=STAGES/'InFrame_Fire_2단계/scene.npz';old=np.load(source)
    np.savez_compressed(dest/'map_support.npz',**{k:old[k] for k in ['support_A','support_B']})
    sha['source_stage2_scene_npz']=hashlib.sha256(source.read_bytes()).hexdigest()
    dump(dest/'provenance.json',dict(source='Microsoft 7-Scenes Fire, Stage 2 map instance support; Stage 3 exact render, collision, navigation and registration files',sha256=sha))
if __name__=='__main__':main()
