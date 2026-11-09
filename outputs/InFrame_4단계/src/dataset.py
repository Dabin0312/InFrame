"""Read behavior cloning data without exposing map/pose/object IDs or validation episodes."""
import json,functools
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
@functools.lru_cache(maxsize=3)
def _sheet(path):
    with Image.open(path) as im:return im.convert('RGB')
def rgb(ep,t):
    s=_sheet(str(ep/f'rgb-{t//64:02}.jpg'));j=t%64;x=j%8*192;y=j//8*144
    return s.crop((x,y,x+192,y+144))
def steps(ep):
    ep=Path(ep);meta=json.loads((ep/'episode.json').read_text());prev=(0.,0.,0)
    for line in (ep/'actions.jsonl').read_text().splitlines():
        r=json.loads(line);t=r['t'];a=r['action']
        if a is None:break
        yield dict(rgb=rgb(ep,t),goal=meta['goal_text'],previous_action=prev,teacher_action=tuple(a),t=t)
        prev=tuple(a)
def training_episodes():
    return [ROOT/'episodes'/s['id'] for s in json.loads((ROOT/'manifest.json').read_text()) if s['use_for_imitation']]
if __name__=='__main__':
    eps=training_episodes();first=next(steps(eps[0]));print(len(eps),'training demonstrations;',first['rgb'].size,first['goal'],first['teacher_action'])
