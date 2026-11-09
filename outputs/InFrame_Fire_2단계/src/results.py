"""Render the measured map, registered masks and all photo-level audit records."""
from pathlib import Path
from html import escape
import argparse, json, io, math
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from PIL import Image,ImageDraw,ImageFont
from geometry import read_masks

PALETTE={'A':(0,135,173),'B':(207,91,13)}
KFONT=Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')

def font(n):
    if KFONT.exists():return ImageFont.truetype(str(KFONT),n,index=0)
    return ImageFont.truetype('DejaVuSans.ttf',n)

def marked(image,links,masks):
    pix=np.array(image.convert('RGB'))
    tags=[]
    for a in links:
        mask=masks[a['mask_index']]
        c=np.array(PALETTE[a['id']]);pix[mask]=(.88*pix[mask]+.12*c).astype(np.uint8)
        contours,_=cv2.findContours(mask.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(pix,contours,-1,tuple(int(v) for v in c),2,cv2.LINE_AA)
        y,x=np.where(mask);tags.append((a['id'],int(np.median(x)),int(np.percentile(y,10))))
    im=Image.fromarray(pix);d=ImageDraw.Draw(im)
    for ident,x,y in tags:
        cx=max(16,min(im.width-16,x));cy=max(16,y-22)
        d.line((cx,cy+10,x,y+3),fill=PALETTE[ident],width=3)
        d.ellipse((cx-13,cy-13,cx+13,cy+13),fill=PALETTE[ident],outline='white',width=2)
        d.text((cx,cy),ident,fill='white',font=font(20),anchor='mm',stroke_width=0)
    return im

def map_plot(out,assets):
    z=np.load(out/'scene.npz');pts=z['xyz'];color=z['rgb']/255.
    assert np.isfinite(pts).all()
    fig,ax=plt.subplots(figsize=(5.4,4.9),dpi=175)
    ax.set_facecolor('#F7F8F4');fig.patch.set_facecolor('white')
    ids=(pts[:,0]>-1.35)&(pts[:,0]<1.35)&(pts[:,2]<2.65)&(pts[:,2]>-.1)
    muted=.50*color[ids]+.42
    ax.scatter(pts[ids,0],pts[ids,2],s=.6,c=muted,alpha=.55,linewidths=0,rasterized=True)
    cams=z['camera_xyz'];ax.plot(cams[:,0],cams[:,2],color='#3f5660',lw=1.6)
    ax.scatter(cams[0,0],cams[0,2],marker='^',s=63,color='#25383C',zorder=4)
    ax.annotate('Camera origin',(0,0),xytext=(7,12),textcoords='offset points',fontsize=8,color='#283B40')
    for a in assets:
        name=a['id'];pts2=z['support_'+name];x,_,depth=a['surface_anchor_xyz_m'];c=np.array(PALETTE[name])/255
        ax.scatter(pts2[:,0],pts2[:,2],c=[c],alpha=.2,s=2,linewidths=0)
        ax.scatter(x,depth,s=55,c=[c],edgecolors='white',zorder=6)
        off=(-30,24) if name=='A' else (15,23)
        ax.annotate(name,(x,depth),xytext=off,textcoords='offset points',color='white',weight='bold',ha='center',va='center',bbox=dict(boxstyle='round,pad=.30',fc=c,ec='none'),arrowprops=dict(arrowstyle='-',lw=1.4,color=c))
    ax.set_xlim(-1.15,1.15);ax.set_ylim(-.22,2.5);ax.set_aspect('equal',adjustable='box')
    ax.set_xlabel('Map X  (m)');ax.set_ylabel('Map Z  (m)')
    ax.grid(alpha=.22,lw=.6);ax.spines[['top','right']].set_visible(False);ax.tick_params(colors='#516364',labelsize=8)
    fig.tight_layout();fig.savefig(out/'map.png',bbox_inches='tight',pad_inches=.14);plt.close(fig)

def overview(out,ev):
    W,H=1450,837
    c=Image.new('RGB',(W,H),'#f4f6f3');d=ImageDraw.Draw(c)
    d.text((40,21),'In Frame   /   7-Scenes Fire',font=font(27),fill='#24595a')
    d.text((38,60),'두 소화기의 지도 위치와 재방문 사진',font=font(48),fill='#162b30')
    d.rounded_rectangle((37,146,625,725),radius=14,fill='white')
    d.text((62,164),'RGB-D로 복원한 지도',font=font(27),fill='#182d36')
    im=Image.open(out/'map.png').convert('RGB');im.thumbnail((535,462));c.paste(im,(330-im.width//2,209))
    d.text((60,681),'첫 카메라 좌표계의 X–Z 투영  ·  단위 m',font=font(21),fill='#405b63')
    for y,key,title in [(146,'seq-01_000000','지도 등록  ·  첫 촬영'),(440,'seq-02_000400','다시 찍은 사진  ·  두 번째 촬영')]:
        d.rounded_rectangle((643,y,1414,y+285),radius=13,fill='white')
        src=Image.open(out/'photos'/f'{key}.jpg')
        if key=='seq-01_000000':
            crop=src.crop((233,10,500,265))
        else:crop=src.crop((389,69,640,318))
        crop.thumbnail((267,251));c.paste(crop,(665,y+17))
        d.text((958,y+31),title,font=font(25),fill='#20373d')
        d.text((958,y+77),'A와 B를 개별 등록' if key=='seq-01_000000' else '화면 안의 A만 연결',font=font(32),fill='#15282e')
        d.text((958,y+139),'A   왼쪽 CO₂ 소화기' if key=='seq-01_000000' else 'B는 화면 오른쪽 밖에 있어',font=font(22),fill='#304c56')
        d.text((958,y+172),'B   오른쪽 Foam 소화기' if key=='seq-01_000000' else '이 사진에 연결되지 않았다.',font=font(22),fill='#304c56')
        d.text((958,y+231),key.replace('_','  /  '),font=font(19),fill='#587277')
    real=ev['real']
    d.text((42,757),f"두 기준점 사이 {ev['anchor_separation_3d_m']*100:.1f} cm      실제 재방문 사진 {real['photos']}장      올바른 연결 {real['correct_mask_and_id']}건 / 보이는 소화기 {real['expected_instances']}건",font=font(27),fill='#20373d')
    c.save(out/'결과.png',optimize=True)

def main():
    p=argparse.ArgumentParser()
    for name in ['scene','cache','controls','out']:p.add_argument(name,type=Path)
    a=p.parse_args();out=a.out;photos=out/'photos';photos.mkdir(exist_ok=True)
    assets=json.loads((out/'map.json').read_text())['objects'];data=json.loads((out/'links.json').read_text());ev=json.loads((out/'evaluation.json').read_text())
    aud={r['photo']:r for r in ev['photos']}
    map_plot(out,assets)
    key='seq-01_000000';_,masks=read_masks(a.cache,key)
    ref=[{'id':asset['id'],'mask_index':obs['mask_index']} for asset in assets for obs in asset['registrations'] if obs['frame']==key]
    marked(Image.open(a.scene/'seq-01/frame-000000.color.png'),ref,masks).save(photos/(key+'.jpg'),quality=92)
    blocks=[];per_asset={asset['id']:[] for asset in assets}
    for rec in data:
        k=rec['photo'];s,i,*_=k.split('_');test=k.startswith('control_')
        path=(a.controls/(k+'.png')) if test else (a.scene/s/('frame-'+i+'.color.png'))
        im=Image.open(path).convert('RGB');im.save(photos/(k+'_rgb.jpg'),quality=91)
        _,masks=read_masks(a.cache,k);marked(im,rec['links'],masks).save(photos/(k+'.jpg'),quality=91)
        r=aud[k]; ids=' '.join(r['predicted']) or '없음';want=' '.join(r['expected']) or '없음'
        for lk in rec['links']:
            per_asset[lk['id']].append(dict(photo=k,image='photos/'+k+'.jpg',source_preview='photos/'+k+'_rgb.jpg',source_sha256=rec['sha256'],mask_index=lk['mask_index'],controlled=test))
        flags=' '.join(r['predicted'])+' '+('control' if test else 'real')+' '+('exact' if r['exact'] else 'miss')
        status='위치 추정 보류' if not r['localized'] else ('판독과 일치' if r['exact'] else '확인 누락 또는 오류')
        blocks.append(f'<article data-flags="{flags}"><a href="photos/{k}.jpg"><img loading="lazy" src="photos/{k}.jpg" alt="{k} 소화기 연결 결과"></a><p><b>{k}</b><br>지도 연결 <strong>{ids}</strong> · 원본 판독 <strong>{want}</strong><br>{status} · <a href="photos/{k}_rgb.jpg">원본 보기</a></p></article>')
    (out/'asset_photos.json').write_text(json.dumps(per_asset,ensure_ascii=False,indent=2)+'\n')
    overview(out,ev)
    r=ev['real'];c=ev['controls']
    html=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>In Frame · Fire 검증</title>
<style>*{{box-sizing:border-box}}body{{margin:auto;max-width:1180px;padding:2rem 1rem 4rem;background:#f7f8f4;color:#193038;font-family:system-ui,sans-serif;line-height:1.55}}h1{{font-size:clamp(1.8rem,5vw,3.2rem);line-height:1.16}}a{{color:#075c70}}header img{{width:100%;height:auto}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:1rem 0}}button{{font:inherit;background:white;border:1px solid #acbabc;padding:.4rem .85rem;border-radius:4px;cursor:pointer}}button[aria-pressed=true]{{background:#22454c;color:white}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:16px}}article{{border:1px solid #d4dfdc;background:white}}article img{{width:100%;display:block}}article p{{margin:10px 14px}}[hidden]{{display:none}}</style><header><h1>소화기별 사진 기록</h1><img src="결과.png" alt="두 소화기의 지도 위치와 다른 촬영분에서 A만 연결한 예"><p>실제 재방문 사진 {r['photos']}장 중 {r['localized']}장의 위치를 찾았다. 보이는 소화기 {r['expected_instances']}건에서 올바른 사진 영역과 ID가 연결된 경우는 {r['correct_mask_and_id']}건, 잘못된 연결은 {r['false_links']}건이다. 가림 대조 {c['photos']}장은 별도 집계했다.</p><p>지도의 좌표는 소화기 겉면에서 추정한 기준점이다. A와 B는 첫 사진의 왼쪽과 오른쪽 설치 위치를 뜻한다. 사진을 누르면 표시된 영역을 확대할 수 있다. <a href="map.json">지도 좌표</a> · <a href="asset_photos.json">설비별 사진 목록</a> · <a href="evaluation.json">전체 검증 수치</a></p></header><nav aria-label="사진 필터">'''
    for f,label in [('real','실제 사진'),('A','A에 연결'),('B','B에 연결'),('miss','누락·오류'),('control','가림 대조')]:
        html+=f'<button type="button" data-filter="{f}" aria-pressed="false">{label}</button>'
    html+='</nav><p id="count" aria-live="polite"></p><main>'+''.join(blocks)+'</main><script>function show(k){let count=0;for(const el of document.querySelectorAll("article")){const f=el.dataset.flags.trim().split(/ +/);el.hidden=!f.includes(k)||(["A","B","miss"].includes(k)&&!f.includes("real"));if(!el.hidden)count++;}for(const b of document.querySelectorAll("button"))b.setAttribute("aria-pressed",b.dataset.filter===k);document.getElementById("count").textContent=count+"장";}document.querySelectorAll("button").forEach(b=>b.onclick=()=>show(b.dataset.filter));show("real");</script></html>'
    (out/'검증사진.html').write_text(html)
if __name__=='__main__':main()
