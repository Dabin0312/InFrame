"""Is the target visible before driving? Includes first visible time in the paired example."""
from world import *
from collections import Counter
def main():
    allruns=json.loads((ROOT/'manifest.json').read_text());events={};summary={}
    for scene in ['castle','fire']:
        w=World(scene,register=False)
        try:
            counts=Counter()
            for e in [v for v in allruns if v['scene']==scene and v['mode']=='teacher']:
                w.reset(np.array(e['start_xyz']),e['start_yaw']);observed={k:v for k,v in w.visible().items() if v['visible']};seen=bool(observed)
                counts['starts']+=1;counts['target_visible_at_start' if seen else 'target_not_visible_at_start']+=1
                if e['success_auto'] and not seen:counts['success_from_not_visible']+=1
                if e['id']=='C-val-023':
                    rows=[json.loads(l) for l in (ROOT/'episodes'/e['id']/'actions.jsonl').read_text().splitlines()]
                    for r in rows:
                        w.reset(np.array(r['xyz']),r['yaw']);hit=w.visible()['C']
                        if hit['visible']:
                            events['C-val-023']=dict(first_visible_step=r['t'],first_visible_s=r['t']*.25,start_visible=seen,pixels=hit['pixels']);break
            summary[scene]=dict(counts)
        finally:w.close()
    dump(ROOT/'start_visibility.json',dict(metric='same depth and registered target support as end visibility, not human/learned detection',scenes=summary,examples=events))
if __name__=='__main__':main()
