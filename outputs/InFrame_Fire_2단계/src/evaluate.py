"""Evaluate frozen, RGB-only predictions against independently marked visible body points."""
from pathlib import Path
import argparse, json
from collections import Counter
import numpy as np
from geometry import dump, read_masks

def summarize(rows):
    counts=Counter()
    for r in rows:
        counts['localized']+=r['localized']
        counts['expected_instances']+=len(r['expected'])
        counts['linked_instances']+=len(r['predicted'])
        counts['correct_mask_and_id']+=len(r['correct'])
        counts['exact_photos']+=r['exact']
    counts['photos']=len(rows)
    counts['false_links']=counts['linked_instances']-counts['correct_mask_and_id']
    counts['missed']=counts['expected_instances']-counts['correct_mask_and_id']
    return dict(counts)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('out',type=Path);p.add_argument('cache',type=Path);p.add_argument('scene',type=Path)
    args=p.parse_args()
    labels=json.loads(Path(__file__).with_name('reference_points.json').read_text())
    records=json.loads((args.out/'links.json').read_text())
    assets=json.loads((args.out/'map.json').read_text())['objects']
    assert [a['id'] for a in assets]==['A','B']
    a,b=[np.array(item['surface_anchor_xyz_m']) for item in assets]
    rows=[];align=np.loadtxt(args.scene/'seq-01/frame-000000.pose.txt')
    for rec in records:
        key=rec['photo']; parts=key.split('_');control=key.startswith('control_')
        if control:
            origin=labels['seq-02_'+parts[1]]
            expected={i:origin[i] for i in 'AB' if parts[-1]==i}
        else:expected=labels[key]
        _,masks=read_masks(args.cache,key)
        correct=[];wrong=[]
        for link in rec['links']:
            obj=link['id'];m=masks[link['mask_index']]
            # A merged region containing the audit points for both assets cannot confirm an ID.
            hits=[i for i,(x,y) in expected.items() if m[y,x]]
            if hits==[obj]:correct.append(obj)
            else:wrong.append(obj)
        predicted=[link['id'] for link in rec['links']]
        assert len(predicted)==len(set(predicted))
        row=dict(photo=key,localized=rec['localized'],expected=list(expected),predicted=predicted,correct=correct,wrong=wrong,
            exact=set(expected)==set(correct) and not wrong)
        if rec['localized'] and not control:
            ref=np.loadtxt(args.scene/parts[0]/('frame-'+parts[1]+'.pose.txt'))
            loc=align@np.array(rec['pose_c2w'])
            row['camera_position_error_m']=float(np.linalg.norm(loc[:3,3]-ref[:3,3]))
        rows.append(row)
    raw=[r for r in rows if not r['photo'].startswith('control_')]
    controls=[r for r in rows if r['photo'].startswith('control_')]
    assert set(r['photo'] for r in raw)==set(labels)
    def coverage(keys):
        selected=[r for r in records if r['photo'] in keys]
        return sorted({ln['id'] for r in selected for ln in r['links']})
    repeated=['control_000000_A','control_000010_A','control_000000_A']
    cases={'A_only_repeated':dict(inputs=repeated,confirmed=coverage(repeated)),
           'A_then_B':dict(inputs=['control_000000_A','control_000010_B'],confirmed=coverage(['control_000000_A','control_000010_B'])),
           'both_hidden':dict(inputs=['control_000000_none','control_000010_none'],confirmed=coverage(['control_000000_none','control_000010_none']))}
    errors=[r['camera_position_error_m'] for r in raw if r['localized']]
    tests=dict(anchor_separation_3d_m=float(np.linalg.norm(a-b)),real=summarize(raw),controls=summarize(controls),
        final_additional_audit=summarize([r for r in raw if r["photo"].startswith("seq-04_") and int(r["photo"].split("_")[1])%125==60]),
        by_capture={s:summarize([r for r in raw if r['photo'].startswith(s)]) for s in ['seq-02','seq-03','seq-04']},
        localized_camera_error_median_m=float(np.median(errors)),localized_camera_error_max_m=float(max(errors)),
        coverage_tests=cases,photos=rows)
    dump(args.out/'evaluation.json',tests)
    print(json.dumps({k:v for k,v in tests.items() if k!='photos'},indent=2))
    print('Review incomplete photos:',[(r['photo'],r['expected'],r['predicted'],r['wrong'],r['localized']) for r in raw if not r['exact']])
if __name__=='__main__':main()
