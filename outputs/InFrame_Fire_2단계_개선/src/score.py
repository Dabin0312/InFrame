"""Score the original and revised systems with identical photo labels."""
from pathlib import Path
import argparse,json,sys
import numpy as np
base=Path(__file__).resolve().parents[2]/'InFrame_Fire_2단계'
sys.path.insert(0,str(base/'src'))
from geometry import dump,read_masks
from evaluate import summarize

def main():
    parser=argparse.ArgumentParser();parser.add_argument('out',type=Path);parser.add_argument('audit_masks',type=Path);a=parser.parse_args()
    read=lambda p:json.loads(p.read_text())
    labels=read(base/'src/reference_points.json');audit=read(Path(__file__).with_name('audit_points.json'));labels.update(audit)
    old=read(base/'links.json')+read(a.out/'audit_baseline.json');new=read(a.out/'links.json')
    initial=read(base/'evaluation.json')['real']
    def score(rows,enhanced):
        result=[]
        for r in rows:
            k=r['photo']; control=k.startswith('control_')
            if control:
                _,i,visible=k.split('_');expected={j:v for j,v in labels['seq-02_'+i].items() if j==visible}
            else:expected=labels[k]
            cache=(a.out/'masks') if enhanced else (a.audit_masks if k in audit else base/'masks')
            _,masks=read_masks(cache,k);correct=[];wrong=[]
            for l in r['links']:
                mask=masks[l['mask_index']];hit=[j for j,(x,y) in expected.items() if mask[y,x]]
                (correct if hit==[l['id']] else wrong).append(l['id'])
            pred=[l['id'] for l in r['links']]
            result.append(dict(photo=k,localized=r['localized'],expected=list(expected),predicted=pred,correct=correct,wrong=wrong,exact=(set(correct)==set(expected) and not wrong)))
        return result
    rows=[score(old,False),score(new,True)]
    result={}; 
    for tag,rr in zip(('baseline','improved'),rows):
        result[tag]={name:summarize([r for r in rr if pred(r['photo'])]) for name,pred in [
            ('original45',lambda k:k.startswith('seq') and k not in audit),('new10',lambda k:k in audit),('controls6',lambda k:k.startswith('control'))]}
    assert result['baseline']['original45']==initial
    result['photos']={'before':rows[0],'after':rows[1]};dump(a.out/'comparison.json',result)
    print({k:v for k,v in result.items() if k!='photos'})
if __name__=='__main__':main()
