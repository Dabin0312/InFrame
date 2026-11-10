"""Verify paired Castle runs and assemble the evidence used by both viewers."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OBJECTS = ['chair', 'trash can', 'fire extinguisher', 'microwave', 'trash can', 'fire extinguisher']
LAYOUTS = {'gallery':'중앙 통로', 'transfer':'기존 재배치', 'fresh':'FRESH-015'}
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_run(run, case, limit):
    trace, audit = run['trace'], run['audit']
    assert trace and len(trace) == run['steps'] <= limit
    assert run['prompt'] == OBJECTS[case] and run['removed'] == (1 if case == 4 else 2 if case == 5 else -1)
    assert run['scoreKey'] == [0,1,2,-1,1,2][case]
    assert run['photo'].startswith('data:image/png;base64,')
    poses = trace[1:] + [run['endpoint']]
    widths = [math.hypot(a['x']-b['x'], a['z']-b['z']) for a,b in zip(trace,poses)]
    assert math.isclose(sum(widths),run['travel'],abs_tol=1e-7)
    assert sum(s['a']==0 and d<1e-7 for s,d in zip(trace,widths)) == run['bumped']
    for i,step in enumerate(trace):
        assert step['logits'][step['a']] >= max(step['logits'])-.00011
        assert step['a'] != 3 or i == len(trace)-1
    assert run['firstStop'] == (trace[-1]['a']==3)
    assert run['end'] == ('stop' if run['firstStop'] else 'step_limit')
    assert run['firstStop'] or len(trace)==limit
    if case < 3:
        x,z=run['anchors'][case];p=run['endpoint']
        assert math.isclose(audit['distance'],math.hypot(x-p['x'],z-p['z']),abs_tol=1e-6)
        assert audit['visible'][case]['pixels']==audit['visiblePixels']
        box=audit['visible'][case]['box']
        center=audit['visiblePixels']>0 and abs((box[0]+box[2])/320-.5)<=.25
        assert center==audit['centered']
        assert run['success']==(run['firstStop'] and audit['distance']<=1.35 and center and audit['visiblePixels']>=80)
    else:
        assert not run['success'] and audit['distance'] is None and audit['visiblePixels']==0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path);parser.add_argument('out',type=Path)
    a=parser.parse_args()
    suite=json.loads((ROOT/'holdout.json').read_text())
    layouts=dict(LAYOUTS);layouts.update({key:'새 배치 '+key[6:] for key in suite['layouts']})
    pairs=[];frozen=json.loads((ROOT/'recovery-fit.json').read_text())
    assert digest(ROOT/'student.onnx') == frozen['onnx_sha256']
    for layout in layouts:
        for case in range(5):
            file=layout+'-'+str(case)+'.json'
            old,new=[json.loads((d/file).read_text()) for d in (a.before,a.after)]
            assert (old['policy'],new['policy'])==('baseline','current')
            for key in ('layout','start','anchors','prompt','removed','scoreKey','firstFrameSHA256'):
                assert old[key]==new[key],(layout,case,key)
            assert old['layout']==layout
            for r in (old,new):
                validate_run(r,case,suite['stepLimit'])
                if layout in suite['layouts']:
                    instance=suite['layouts'][layout];assert r['anchors']==instance['anchors'] and r['start']==instance['start']
            pairs.append({'layout':layout,'case':case,'before':old,'after':new})
    for layout in layouts:
        assert len({p['before']['firstFrameSHA256'] for p in pairs if p['layout']==layout and p['case']<4})==1
    def measure(selected,field):
        return dict(total=len(selected),**{v:sum(p[v][field] for p in selected) for v in ['before','after']})
    unseen=[p for p in pairs if p['layout'] in suite['layouts']]
    metrics=dict(holdoutPositive=measure([p for p in unseen if p['case']<3],'success'),
                 holdoutAbsent=measure([p for p in unseen if p['case']>=3],'firstStop'))
    result=dict(scene='Skokloster Castle',holdoutSHA256=digest(ROOT/'holdout.json'),oldModelSHA256=digest(ROOT/'baseline.onnx'),newModelSHA256=frozen['onnx_sha256'],
                layouts=layouts,metrics=metrics,pairs=pairs)
    a.out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(metrics))
if __name__=='__main__':main()
