"""Package the paired offline replays and a compact side-by-side video from recorded RGBs."""
import argparse,csv,json,math,shutil,subprocess
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];PRIOR=ROOT.parent/'InFrame_4단계'
HOME_FONT='/System/Library/Fonts/AppleSDGothicNeo.ttc'
NAMES=['현재 한 프레임','최근 4스텝']
REASONS={'success':'성공','timeout':'시간 초과','collision_limit':'충돌 3회','goal_out_of_view':'시야 밖 정지','stopped_too_far':'너무 이른 정지'}
def js(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def directory(r):return ROOT/'episodes'/f"h{r['history']}"/r['start_id']
def trace(r):
    rows=[json.loads(x) for x in (directory(r)/'steps.jsonl').read_text().splitlines()];count=0;out=[]
    for v in rows:
        count+=v['collision']
        out.append([round(v['xyz'][0],5),round(v['xyz'][2],5),round(v['yaw'],6),v['action'],count])
    return out
@lru_cache(maxsize=4)
def sheet(p):
    with Image.open(p) as im:return im.convert('RGB')
def rgb(r,i):
    j=i%64;x=j%8*192;y=j//8*144
    return sheet(directory(r)/f'rgb-{i//64:02}.jpg').crop((x,y,x+192,y+144))
def text(draw,xy,s,sz=18,c='#e9eeec'):
    draw.text(xy,s,fill=c,font=ImageFont.truetype(HOME_FONT,sz))
def clip(pair,ffmpeg):
    w,h=880,466;dark='#101c25';sc=[(80,198,163),(173,147,229)]
    last=max(r['observations'] for r in pair)-1
    indices=list(range(0,last+1,2))
    if indices[-1]!=last:indices.append(last)
    proc=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','12','-i','-','-c:v','libx264','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/'학생주행_비교.mp4')],stdin=subprocess.PIPE)
    for tick in indices:
        canvas=Image.new('RGB',(w,h),dark);draw=ImageDraw.Draw(canvas)
        text(draw,(14,8),'같은 출발점에서 본 학생 정책의 주행',26)
        text(draw,(647,16),pair[0]['start_id']+'   ·   6배속',17)
        for j,r in enumerate(pair):
            x=14+j*434;i=min(tick,r['observations']-1);end=i==r['observations']-1
            text(draw,(x,49),NAMES[j],21,sc[j])
            canvas.paste(rgb(r,i).resize((418,314),Image.Resampling.BILINEAR),(x,84))
            label=REASONS[r['reason']] if end else '주행 중'
            text(draw,(x,403),f'{i*.25:.2f} s  ·  '+label,21)
            if end:text(draw,(x,437),f"관측점까지 {r['final_geo_m']['C']:.2f} m  ·  "+('C 확인' if r['visible_ids'] else 'C 미확인'),16)
        b=canvas.tobytes();proc.stdin.write(b)
        if tick==last:
            canvas.save(ROOT/'학생주행_정지비교.jpg',quality=93)
            for _ in range(22):proc.stdin.write(b)
    proc.stdin.close()
    assert proc.wait()==0
def main(ffmpeg):
    summary=json.loads((ROOT/'results.json').read_text());pairs=json.loads((ROOT/'paired_runs.json').read_text())
    view=ROOT/'viewer';view.mkdir(exist_ok=True)
    shutil.copy2(PRIOR/'viewer/castle.png',view/'castle.png')
    cal=PRIOR/'calibration/castle';v=np.load(cal/'floor.npz')['v'][:,[0,2]];a=np.array(list(json.loads((cal/'views.json').read_text())['objects'].values()))[:,[0,2]]
    pts=np.vstack([v,a]);lo=pts.min(0);hi=pts.max(0);scale=float(min(492/(hi-lo)))
    transform=dict(scale=scale,offset=(np.array([560,560])/2-(lo+hi)/2*scale).tolist())
    # Prefer a disagreement with travel and a non-timeout failure to keep the preview concise.
    def rank(p):
        return (p[0]['success']!=p[1]['success'],all(r['reason']!='timeout' for r in p),sum(r['success'] for r in p)>0,min(p[0]['start_geo_m'],10))
    chosen=max(pairs,key=rank)
    for pair in pairs:
        name=pair[0]['start_id'];(view/f'{name}.js').write_text(f'window.traces[{js(name)}]='+js([trace(r) for r in pair])+';')
    (view/'index.js').write_text('const pairs='+js(pairs)+';const summary='+js(summary)+';const example='+js(chosen[0]['start_id'])+';const transform='+js(transform)+';')
    shutil.copy2(Path(__file__).with_name('replay.html'),ROOT/'학생주행_재생.html')
    with (ROOT/'출발점별_결과.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['출발점','최초 C 가시','출발 최단거리 m']+[f'{h}스텝 {label}' for h in [1,4] for label in ['결과','STOP','종료 거리 m','충돌','주행 m','SPL']])
        for pair in pairs:
            row=[pair[0]['start_id'],pair[0]['initially_visible'],pair[0]['start_geo_m']]
            for r in pair:row.extend([REASONS[r['reason']],r['stop'],r['final_geo_m']['C'],r['collisions'],r['travel_m'],r['spl']])
            writer.writerow(row)
    if ffmpeg:clip(chosen,ffmpeg)
    print('featured',chosen[0]['start_id'],[(r['reason'],r['travel_m'],r['final_geo_m']) for r in chosen])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ffmpeg');main(p.parse_args().ffmpeg)
