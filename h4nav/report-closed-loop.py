"""Build the website data, standalone viewer, and lossless per-step record bundle."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
def build(suite_file,runs,dest):
    suite=json.loads(suite_file.read_bytes())
    audit=json.loads((runs/'audit.json').read_bytes())
    digest=hashlib.sha256(suite_file.read_bytes()).hexdigest()
    assert audit['suiteHash']==digest and len(audit['cases'])==len(suite['layouts'])*6
    tris=json.loads((ROOT/'../spatial/floor.json').read_bytes())['tris']
    outline=''.join('M'+'L'.join(f'{x:.3f},{z:.3f}' for x,y,z in tri)+'Z' for tri in tris)
    xs=[x for tri in tris for x,y,z in tri];zs=[z for tri in tris for x,y,z in tri]
    box=[min(xs)-.5,min(zs)-.5,max(xs)-min(xs)+1,max(zs)-min(zs)+1]
    data=dict(layouts=suite['layouts'],runs=[],floor=outline,viewBox=' '.join(map(str,box)),
              frames=sum(r['frames'] for r in audit['cases']))
    dest.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(dest/'InFrame_Go2_closed_loop_records.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(suite_file,'holdout.json');bundle.write(runs/'audit.json','audit.json')
        files=[ROOT/'transfer-h4.onnx',ROOT/'../spatial/prompt-vision.onnx',
               *sorted((ROOT/'../spatial').glob('prompt-text-*.bin')),
               ROOT/'../spatial/castle.glb',ROOT/'../spatial/chair.glb',ROOT/'../spatial/bin.glb',
               ROOT/'../outputs/InFrame_7단계/src/multigoal.py',ROOT/'../outputs/InFrame_7단계/src/bridge.py']
        manifest={str(p.resolve().relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        bundle.writestr('model-and-scene-sha256.json',json.dumps(manifest,indent=2))
        for case in audit['cases']:
            f=runs/(case['id']+'.json')
            bundle.write(f,'runs/'+f.name)
            r=json.loads(f.read_bytes());assert r['suiteHash']==digest
            row={k:r[k] for k in ('layout','goal','removed','stopped','end','traveled','blocked','photo','audit')}
            route=[]
            for pos in [r['start'],*(s['after'] for s in r['steps'])]:
                point=[round(pos['x'],4),round(pos['z'],4)]
                if not route or route[-1]!=point:route.append(point)
            n=len(r['steps']);row.update(path=route,n=n,time=(n-int(r['stopped']))*suite['period'])
            data['runs'].append(row)
    shutil.copyfile(dest/'InFrame_Go2_closed_loop_records.zip',ROOT/'closed-loop-records.zip')
    js='window.closedLoop='+json.dumps(data,ensure_ascii=False,separators=(',',':'))+';\n'
    (ROOT/'closed-loop-data.js').write_text(js)
    html=(ROOT/'closed-loop.html').read_text().replace('<script src="closed-loop-data.js"></script>','<script>'+js+'</script>')
    (dest/'InFrame_Go2_closed_loop.html').write_text(html.replace('href="closed-loop-records.zip"','href="InFrame_Go2_closed_loop_records.zip"'))
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ['suite','runs','dest']:p.add_argument(key,type=Path)
    a=p.parse_args();build(a.suite,a.runs,a.dest)
