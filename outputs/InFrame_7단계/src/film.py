"""Render side-by-side normal and camera-cut episodes from the recorded simulator RGB and RPC logs."""
import argparse
import gzip
import json
from functools import lru_cache
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
SIZE=(1120,620)
BG='#122325'
PANEL='#1e3233'
TEXT='#f2f4e8'
MUTED='#b5c9bd'
MINT='#95eec4'
AMBER='#ffd395'

@lru_cache(maxsize=16)
def font(size):
    return ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc',size)


def label(draw,xy,text,size=18,color=TEXT):
    draw.text(xy,text,font=font(size),fill=color)


def main(ffmpeg):
    base=ROOT/'results/habitat'
    case='FRESH-015'
    report=json.loads((base/'report.json').read_text())
    cutoff=report['camera_cut']
    last_capture=cutoff['last_rgb_s']
    stop_time=cutoff['stop_s']
    traces=[json.load(gzip.open(base/'traces'/kind/(case+'.json.gz'),'rt'))['steps'] for kind in ('normal','cut')]
    images=[np.load(base/'media'/(case+s+'.npz'))['rgb'] for s in ('-rgb','-cut-monitor')]
    assert all(len(x)==len(y) for x,y in zip(images,traces))
    dest=ROOT/'media'
    dest.mkdir(exist_ok=True)
    final=traces[0][-1]['t']
    snapshots={}
    with subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                           '-s','1120x620','-r','12','-i','-','-c:v','libx264','-pix_fmt','yuv420p',
                           '-crf','19','-movflags','+faststart',str(dest/'정상주행_카메라단절.mp4')],stdin=subprocess.PIPE) as enc:
        # Each 4 Hz observation lasts 3 video frames at 12 fps, preserving original time.
        for n,row in enumerate(traces[0]):
            t=row['t']
            canvas=Image.new('RGB',SIZE,BG)
            d=ImageDraw.Draw(canvas)
            label(d,(24,14),'InFrame   /   Go2 명령 검증',29)
            label(d,(24,56),'FRESH-015   ·   Habitat-Sim   ·   같은 출발점과 소화기 C',18,MUTED)
            label(d,(917,30),f'{t:05.2f} / {final:.2f} s',19,MINT)
            for j in range(2):
                x=24+j*545
                i=min(n,len(traces[j])-1)
                r=traces[j][i]
                d.rounded_rectangle((x,98,x+526,552),radius=10,fill=PANEL)
                label(d,(x+16,107),['정상 카메라','주행 중 카메라 단절'][j],21)
                is_off=j==1 and t>last_capture
                if is_off:
                    tag='입력 없음'
                else:
                    tag='RGB 수신'
                label(d,(x+404,112),tag,17,AMBER if is_off else MINT)
                picture=Image.fromarray(images[j][i]).resize((416,312),Image.Resampling.BILINEAR)
                canvas.paste(picture,(x+55,148))
                if is_off:
                    d.rounded_rectangle((x+62,155,x+326,184),radius=4,fill='#283231')
                    label(d,(x+69,158),'검증용 시점 · 정책에는 미전달',16,AMBER)
                vx,_,yaw=r['sent']
                if r['state']=='goal_stop':
                    state='StopMove()   ·   소화기 확인'
                elif r['state']=='frame_timeout':
                    state='StopMove()   ·   카메라 타임아웃'
                else:
                    state=f'Move({vx:.2f}, 0, {yaw:+.2f})'
                label(d,(x+17,467),state,22,MINT if j==0 else AMBER)
                if j==1 and t>traces[1][-1]['t']:
                    stats='종료 화면 유지   ·   정지 후 1.00초 위치 검증'
                else:
                    stats=f"이동 {r['travel_m']:.2f} m   ·   충돌 {r['total_hits']}회"
                    if is_off and t<stop_time:
                        stats+='   ·   마지막 명령 유지'
                label(d,(x+17,510),stats,17,MUTED)
            text=f'마지막 RGB {last_capture:.2f}초   →   자동 정지 {stop_time:.2f}초   ·   감지 대기 중 {cutoff["travel_during_silence_m"]:.2f} m 전진'
            label(d,(26,574),text,20)
            raw=canvas.tobytes()
            for _ in range(3 if t<final else 19):
                enc.stdin.write(raw)
            if t in (last_capture,stop_time,final):
                snapshots[t]=canvas
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError('Could not encode MP4')
    snapshots[final].save(dest/'종료비교.jpg',quality=92)
    snapshots[stop_time].save(dest/'자동정지_시점.jpg',quality=92)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('ffmpeg')
    main(p.parse_args().ffmpeg)
