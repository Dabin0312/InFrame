"""Offline paired replay, event index and MP4s generated from recorded observations."""
import argparse
import csv
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import ROOT, S4, S5, WORK, read

VIEW = ROOT / 'viewer'
MODES = ('before', 'after')
LABELS = ('개선 전', '개선 후')
STATUS = {'success':'성공', 'rotation':'제자리 회전 · 시간 초과', 'boundary':'경계 충돌 3회',
          'other_timeout':'시간 초과', 'goal_out_of_view':'시야 밖 정지', 'stopped_too_far':'이른 정지'}
CLIPS = [
    ('미사용', 'FRESH-015', '경계 충돌', '새출발점_경계충돌.mp4'),
    ('미사용', 'FRESH-045', '제자리 회전', '새출발점_제자리회전.mp4'),
    ('미사용', 'FRESH-014', '남은 실패', '새출발점_남은실패.mp4'),
    ('학습', 'LEARN-008', '경계 충돌', '학습구역_경계충돌.mp4'),
    ('학습', 'LEARN-009', '제자리 회전', '학습구역_제자리회전.mp4'),
]

def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def read_trace(episode):
    rows = [json.loads(s) for s in (episode/'steps.jsonl').read_text().splitlines()]
    total = 0
    first_hit = None
    trace = []
    for row in rows:
        x, _, z = row['xyz']
        trace.append([round(x,5), round(z,5), round(row['yaw'],6), row['action'], total])
        if row['collision']:
            total += 1
            if first_hit is None:
                first_hit = row['t']+1
    tail = [s['action'][1] for s in rows[-81:-1] if s['action'] is not None]
    flips = sum(a*b < 0 for a,b in zip(tail,tail[1:]))
    return trace, first_hit, flips

@lru_cache(maxsize=8)
def image_sheet(path):
    with Image.open(path) as im:
        return im.convert('RGB')

@lru_cache(maxsize=12)
def font(size):
    return ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc', size)

def encode_clip(output, title, base, pair, ffmpeg):
    traces = [read_trace(base/r['variant']/r['start_id'])[0] for r in pair]
    last = max(len(t) for t in traces)-1
    ticks = sorted(set(range(0,last+1,2)) | {last})
    with subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                           '-s','900x466','-r','12','-i','-','-c:v','libx264','-crf','19','-pix_fmt','yuv420p',
                           '-movflags','+faststart',str(output)], stdin=subprocess.PIPE) as proc:
        for tick in ticks:
            canvas = Image.new('RGB',(900,466),'#152722')
            draw = ImageDraw.Draw(canvas)
            draw.text((15,8),title+'  ·  '+pair[0]['start_id'],font=font(24),fill='white')
            draw.text((725,15),'Habitat-Sim  ·  6×',font=font(18),fill='#c8d8d0')
            for j,(r,trace) in enumerate(zip(pair,traces)):
                i = min(tick,len(trace)-1)
                finished = i==len(trace)-1
                x = 14+j*448
                episode = base/r['variant']/r['start_id']
                if finished:
                    with Image.open(episode/'last.png') as im:
                        image = im.copy()
                else:
                    image = image_sheet(episode/f'rgb-{i//64:02}.jpg')
                    u, v = (i%8)*192, ((i%64)//8)*144
                    image = image.crop((u,v,u+192,v+144))
                draw.text((x,46),LABELS[j]+'  ·  4스텝',font=font(20),fill=('#8be2bb','#d1a5f8')[j])
                canvas.paste(image.resize((420,315),Image.Resampling.BILINEAR),(x,81))
                phase = STATUS[r['kind']] if finished else '주행 중'
                draw.text((x,399),f'{i*.25:.2f}초   ·   {phase}   ·   충돌 {trace[i][4]}회',font=font(20),fill='white')
                if finished:
                    seen = '소화기 보임' if r['visible_ids'] else '소화기 미확인'
                    draw.text((x,432),f"관측점까지 {r['final_geo_m']['C']:.2f} m   ·   {seen}",font=font(17),fill='#c8d8d0')
            raw = canvas.tobytes()
            proc.stdin.write(raw)
            if tick==last:
                for _ in range(18):
                    proc.stdin.write(raw)
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError(f'Video encoding failed: {output}')

def csv_results(path, pairs):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['출발점','출발 X m','출발 Y m','출발 Z m','출발 yaw rad','최초 가시','시작 관측점 거리 m']+
                        [m+' '+v for m in LABELS for v in ('결과','STOP','마지막 가시','종료 관측점 거리 m','주행 m','시간 s','충돌','SPL')])
        for a,b in pairs:
            row = [a['start_id'],*a['start_xyz'],a['start_yaw'],a['initially_visible'],a['start_geo_m']]
            for r in (a,b):
                row.extend([STATUS[r['kind']],r['stop'],bool(r['visible_ids']),r['final_geo_m']['C'],
                            r['travel_m'],r['elapsed_s'],r['collisions'],r['spl']])
            writer.writerow(row)

def main(ffmpeg):
    VIEW.mkdir(exist_ok=True)
    shutil.copy2(S4/'viewer/castle.png',VIEW/'castle.png')
    shutil.copy2(S5/'checkpoints/student-4.pt',ROOT/'weights/before.pt')
    # Bundle the frozen backbone architecture so the RGB worker can run on its own.
    shutil.copy2(S5/'src/policy.py',ROOT/'src/policy.py')
    cal = S4/'calibration/castle'
    points = np.vstack([np.load(cal/'floor.npz')['v'][:,[0,2]],np.array(list(read(cal/'views.json')['objects'].values()))[:,[0,2]]])
    lo,hi = points.min(axis=0),points.max(axis=0)
    scale = float(min(492/(hi-lo)))
    projection = dict(scale=scale,offset=(280-(lo+hi)*scale/2).tolist())
    fresh = read(ROOT/'시험_쌍별.json')
    train = read(WORK/'train_pairs.json')
    csv_results(ROOT/'새출발점_60곳.csv', fresh)
    csv_results(ROOT/'학습구역_132곳.csv', train)
    for pair in fresh:
        key = pair[0]['start_id']
        traces = []
        for r in pair:
            trace,first,flips = read_trace(ROOT/'episodes'/r['variant']/key)
            r.update(first_hit=first,tail_flips=flips)
            traces.append(trace)
        (VIEW/(key+'.js')).write_text(f'window.routes[{compact(key)}]={compact(traces)};\n')
    index = {p[0]['start_id']:p for p in (fresh+train)}
    clips = []
    for split,key,topic,filename in CLIPS:
        title = split+' 출발점 · '+topic
        if ffmpeg:
            base = WORK/'train' if split=='학습' else ROOT/'episodes'
            encode_clip(ROOT/filename, title, base, index[key],ffmpeg)
        clips.append(dict(file=filename,label=title+' ('+key+')'))
    variables = dict(runs=fresh,projection=projection,featured='FRESH-015',examples=clips)
    (VIEW/'data.js').write_text('\n'.join(f'const {k}={compact(v)};' for k,v in variables.items())+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--ffmpeg',type=Path)
    main(parser.parse_args().ffmpeg)
