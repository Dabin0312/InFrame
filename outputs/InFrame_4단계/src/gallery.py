"""Package offline click-through replay with map, robot RGB and real command at every recorded tick."""
import json, math, shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from dataset import ROOT
def compact(o):return json.dumps(o,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def font(size):
    try:return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',size)
    except OSError:return ImageFont.truetype('DejaVuSans-Bold.ttf',size)
def make():
    assets=ROOT/'viewer';assets.mkdir(exist_ok=True);episodes=json.loads((ROOT/'manifest.json').read_text());maps={}
    for name in ['fire','castle']:
        d=ROOT/'calibration'/name;meta=json.loads((d/'views.json').read_text());floor=np.load(d/'floor.npz');verts=floor['v'][:,[0,2]]
        a=np.array(list(meta['objects'].values()))[:,[0,2]]
        allp=np.vstack([verts,a]);lo=allp.min(0);hi=allp.max(0);scale=min(492/np.maximum(hi-lo,1e-5));offset=np.array([560,560])/2-(lo+hi)/2*scale
        def xy(x):return tuple(np.rint(np.asarray(x)*scale+offset).astype(int))
        im=Image.new('RGB',(560,560),'#101b24');draw=ImageDraw.Draw(im)
        spacing=.1 if name=='fire' else 2
        for axis in [0,1]:
            for x in np.arange(-100,100,spacing):
                pos=x*scale+offset[axis]
                if 0<pos<560:draw.line([(pos,0),(pos,560)] if axis==0 else [(0,pos),(560,pos)],fill='#1b2b36')
        for tri in floor['t']:draw.polygon([xy(verts[i]) for i in tri],fill='#3a5261')
        bar=.1 if name=='fire' else 2;length=bar*scale;draw.line([(22,526),(22+length,526)],fill='#e7eceb',width=3);draw.text((22,532),f'{bar:g} m',font=font(12),fill='#dae8e7')
        for k,rs in meta['views'].items():
            for r in rs:
                x,y=xy(np.array(r['xyz'])[[0,2]]);draw.ellipse((x-4,y-4,x+4,y+4),outline='#ffffff',width=2)
        for k,pos in meta['objects'].items():
            x,y=xy(np.array(pos)[[0,2]]);draw.ellipse((x-6,y-6,x+6,y+6),fill='#ff814f',outline='white',width=1)
            draw.text((x+8,y-8),k,font=font(16),fill='#ffb28e',stroke_width=2,stroke_fill='#101b24')
        im.save(assets/(name+'.png'));maps[name]=dict(scale=scale,offset=offset.tolist())
    for s in episodes:
        ep=ROOT/'episodes'/s['id'];rows=[json.loads(l) for l in (ep/'actions.jsonl').read_text().splitlines()]
        seq=[[round(r['xyz'][0],5),round(r['xyz'][2],5),round(r['yaw'],5),r['action'],r['collision']] for r in rows]
        (ep/'replay.js').write_text('window.traces['+compact(s['id'])+']='+compact(seq)+';')
    (assets/'index.js').write_text('const runs='+compact(episodes)+';const maps='+compact(maps)+';')
    shutil.copyfile(Path(__file__).with_name('replay.html'),ROOT/'주행재생.html')
if __name__=='__main__':make()
