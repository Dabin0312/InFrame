import json,math,shutil,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from dataset import ROOT,rgb
EP=ROOT/'episodes'
FONT='/System/Library/Fonts/AppleSDGothicNeo.ttc'
def font(n):return ImageFont.truetype(FONT,n,index=0)
def txt(draw,xy,t,size=19,fill='#eaf2f1'):draw.text(xy,t,font=font(size),fill=fill)
def meta(id):return json.loads((EP/id/'episode.json').read_text())
def paint_comparison():
    im=Image.new('RGB',(1112,414),'#101d26');d=ImageDraw.Draw(im)
    txt(d,(22,11),'같은 출발점에서 소화기를 확인한 세 가지 결과',29)
    txt(d,(23,50),'Skokloster 성  /  목표 C  /  아래 사진은 각 주행의 마지막 로봇 RGB',17,'#b7cbd0')
    for j,(id,title) in enumerate([('C-val-023','정상 정지'),('X-C-early_stop','너무 이른 정지'),('X-C-look_away','소화기를 등지고 정지')]):
        s=meta(id);x=22+363*j
        im.paste(Image.open(EP/id/'last.png').resize((342,249),Image.Resampling.LANCZOS),(x,88))
        co='#9de7c7' if s['success_auto'] else '#ffaf90';txt(d,(x,339),title,22,co)
        txt(d,(x,374),f"관측점까지 {min(s['final_geo_m'].values()):.2f} m  ·  "+('C 확인' if s['visible_ids'] else 'C 미확인'),17)
    im.save(ROOT/'같은출발_정지비교.jpg',quality=94)
def make_video(id,out,ff):
    s=meta(id);ep=EP/id;rows=[json.loads(r) for r in (ep/'actions.jsonl').read_text().splitlines()]
    bg=Image.open(ROOT/'viewer'/f"{s['scene']}.png").resize((328,328),Image.Resampling.LANCZOS)
    v=np.load(ROOT/'calibration'/s['scene']/'floor.npz')['v'][:,[0,2]];m=json.loads((ROOT/'calibration'/s['scene']/'views.json').read_text())
    pts=np.vstack([v,np.array(list(m['objects'].values()))[:,[0,2]]]);lo=pts.min(0);hi=pts.max(0);sc=min(492/(hi-lo));offset=np.array([560,560])/2-(lo+hi)/2*sc
    def point(row):
        v=(np.array(row['xyz'])[[0,2]]*sc+offset)*328/560;return (v[0]+468,v[1]+57)
    trace=[point(r) for r in rows];proc=subprocess.Popen([ff,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','806x454','-r','12','-i','-','-c:v','libx264','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(ROOT/out)],stdin=subprocess.PIPE)
    for i,r in enumerate(rows):
        im=Image.new('RGB',(806,454),'#101d26');d=ImageDraw.Draw(im);txt(d,(15,9),'InFrame   /   지도 기반 교사 주행',25)
        txt(d,(470,16),'Skokloster 성   ·   소화기 C',18,'#b9cecf')
        im.paste(rgb(ep,i).resize((438,328),Image.Resampling.BILINEAR),(14,57));im.paste(bg,(468,57))
        if i:d.line(trace[:i+1],fill='#8ceacc',width=3)
        x,y=trace[i];yaw=r['yaw'];f=np.array([-math.sin(yaw),-math.cos(yaw)]);n=np.array([f[1],-f[0]]);p=np.array([x,y]);d.polygon([tuple(p+f*8),tuple(p-f*5+n*5),tuple(p-f*5-n*5)],fill='#ff976e' if r['collision'] else '#a9ffdf',outline='#0b1b1e')
        a=r['action'];msg='충돌 3회 · 강제 종료' if a is None else 'STOP · 소화기 C 확인' if a[2] and s['success_auto'] else 'STOP' if a[2] else '전진' if a[0] else '좌회전' if a[1]>0 else '우회전'
        txt(d,(15,397),msg,24,'#a7edcd' if s['success_auto'] or i<len(rows)-1 else '#ffb092')
        txt(d,(323,404),f'{i*.25:.2f} s  /  {s["duration_s"]:.2f} s     ·     충돌 {sum(q["collision"] for q in rows[:i+1])}회     ·     3배속',18)
        b=im.tobytes();proc.stdin.write(b)
        if i==len(rows)-1:
            for j in range(23):proc.stdin.write(b)
    proc.stdin.close();assert proc.wait()==0
if __name__=='__main__':
    paint_comparison();ff=sys.argv[1] if len(sys.argv)>1 else shutil.which('ffmpeg')
    make_video('C-val-023','성공_10m주행.mp4',ff);make_video('C-train-102','실패_충돌3회.mp4',ff)
