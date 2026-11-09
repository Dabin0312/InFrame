"""Render real sensor, geometry and Habitat action traces for inspection."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.patches import Patch,Circle
from PIL import Image,ImageDraw,ImageFont
from io import BytesIO

FONT='/System/Library/Fonts/AppleSDGothicNeo.ttc'
K=FontProperties(fname=FONT)
BLUE='#1D7298';AMBER='#D26D19';TEAL='#215c64';INK='#20343c'
COLORS=np.array([[233,237,235],[238,246,223],[185,148,118]],np.uint8)

def font(n):
    return ImageFont.truetype(FONT,n)
def read(p):return json.loads(p.read_text())
def photo_label(im,xy,tag,color):
    draw=ImageDraw.Draw(im);x,y=map(int,xy)
    draw.ellipse((x-14,y-14,x+14,y+14),fill=color,outline='white',width=2)
    draw.text((x,y),tag,font=font(21),fill='white',anchor='mm')

def map_panel(ax,d,r,align,probes=True):
    g=d['grid'];o=d['origin'];s=float(d['cell']);H,W=g.shape
    ax.imshow(COLORS[g],origin='upper',interpolation='nearest',extent=[o[0],o[0]+s*W,-o[1]-s*H,-o[1]])
    for isl in r['islands']:
        tri=np.array(isl['vertices'])[np.array(isl['triangles'])]
        from matplotlib.collections import PolyCollection
        xy=tri[:,:,[0,2]].copy();xy[:,:,1]*=-1
        ax.add_collection(PolyCollection(xy,facecolors='#227B76',edgecolors='none'))
    a=r['targets']['A'];trace=np.array(a['trace']);ax.plot(trace[:,0],-trace[:,2],lw=2.4,color='#fcfcf8',zorder=5)
    ax.plot(trace[0,0],-trace[0,2],'o',color='#23333b',ms=5,zorder=7)
    ax.annotate('출발',(trace[0,0],-trace[0,2]),(-28,-17),textcoords='offset points',fontproperties=K,color=INK)
    ax.plot(trace[-1,0],-trace[-1,2],'D',ms=6,color='#213c57',mec='white',zorder=8)
    ax.annotate('관측 지점',(trace[-1,0],-trace[-1,2]),(6,9),textcoords='offset points',fontproperties=K,color=INK)
    for key,c,off in [('A',BLUE,(-15,14)),('B',AMBER,(7,13))]:
        x,_,z=align['assets'][key]['sim_xyz_m'];ax.scatter(x,-z,c=c,s=44,edgecolors='white',zorder=5)
        ax.annotate(key,(x,-z),off,textcoords='offset points',color=c,fontweight='bold')
    if probes:
        for i,text,off in [(3,'표지판',(14,-15)),(4,'옷걸이 쪽',(-58,12))]:
            pr=r['probes'][i];x,z=pr['nearest_obstacle_xz']
            ax.scatter(x,-z,marker='x',s=46,color='#83402a',zorder=7)
            ax.annotate(text,(x,-z),off,textcoords='offset points',fontproperties=K,color='#653924',arrowprops=dict(arrowstyle='-',color='#955c49',lw=.7))
        u=r['probes'][-1];x,y,z=u['start'];x1,y,z1=u['requested']
        ax.annotate('',(x1,-z1),(x,-z),arrowprops=dict(arrowstyle='->',ls=':',color='#626f75',lw=1.3))
        ax.annotate('미관측 방향',(x1,-z1),(5,0),textcoords='offset points',fontproperties=K,color='#475a61')
    ax.set_xlim(-1.30,.74);ax.set_ylim(.40,1.99);ax.set_aspect('equal')
    ax.set_xlabel('X (m)',color=INK);ax.set_ylabel('−Z (m)',color=INK);ax.tick_params(labelsize=8,color='#c2cdca')
    for sp in ax.spines.values():sp.set_color('#d2dada')

def main():
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('scene',type=Path);ar=p.parse_args();out=ar.out
    d=np.load(out/'observations.npz');r=read(out/'simulation.json');al=read(out/'alignment.json');t=r['targets']['A']
    fig=plt.figure(figsize=(11.7,6.4),layout='constrained',dpi=160);fig.set_facecolor('white')
    gs=fig.add_gridspec(2,2,width_ratios=[1.48,1],height_ratios=[1,1]);ax=fig.add_subplot(gs[:,0]);map_panel(ax,d,r,al)
    ax.set_title('Fire  |  원래 지도 위의 주행 경로',loc='left',fontproperties=K,fontsize=18,color=INK,pad=12)
    handles=[Patch(color=c,label=l) for c,l in [('#227B76','로봇 중심 가능'),('#eef6df','관측 바닥'),('#b99476','장애물'),('#e9edeb','미관측')]]
    ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.11),ncol=4,frameon=False,prop=FontProperties(fname=FONT,size=9),columnspacing=1,handlelength=1)
    for i,(im,title) in enumerate([(Image.open(ar.scene/'seq-01/frame-000000.color.png').convert('RGB'),'첫 촬영분 · 지도에 등록한 A와 B'),(Image.open(out/'approach_A.png').convert('RGB'),'도착한 로봇의 카메라 · Habitat-Sim RGB')]):
        if i==0:
            for tag,c in [('A',BLUE),('B',AMBER)]:
                src=np.array(al['assets'][tag]['map_xyz_m']);photo_label(im,src[:2]*585/src[2]+[320,240],tag,c)
        else:
            for tag,c in [('A',BLUE),('B',AMBER)]:photo_label(im,t['depth_visibility'][tag]['median_visible_xy'],tag,c)
        ax2=fig.add_subplot(gs[i,1]);ax2.imshow(im);ax2.axis('off');ax2.set_title(title,loc='left',fontproperties=K,fontsize=12,color=INK)
    fig.savefig(out/'주행검증.png',facecolor='white');plt.close(fig)
    z=np.load(out/'camera_trace.npz');arr=z['rgb'];pts=z['xyz'];gif=[];drawn=[]
    # Fixed top-down viewport, real poses and recorded agent RGB at each frame.
    o=d['origin'];s=float(d['cell']);bg=Image.fromarray(COLORS[d['grid']]).resize((560,376),Image.Resampling.NEAREST)
    def loc(x,z):return ((x-o[0])/s/d['grid'].shape[1]*560,(z-o[1])/s/d['grid'].shape[0]*376)
    for j,(rgb,pt) in enumerate(zip(arr,pts)):
        canvas=Image.new('RGB',(978,443),'#f7f8f4');m=bg.copy();md=ImageDraw.Draw(m)
        for isl in r['islands']:
            vs=np.array(isl['vertices'])
            for tri in isl['triangles']:md.polygon([loc(vs[k,0],vs[k,2]) for k in tri],fill='#397f78')
        for k,c in [('A',BLUE),('B',AMBER)]:
            x,_,zz=al['assets'][k]['sim_xyz_m'];u,v=loc(x,zz);md.ellipse((u-10,v-10,u+10,v+10),fill=c);md.text((u,v),k,font=font(16),anchor='mm',fill='white')
        drawn.append(loc(pt[0],pt[2]))
        if len(drawn)>1:md.line(drawn,fill='white',width=3)
        u,v=drawn[-1];md.ellipse((u-5,v-5,u+5,v+5),fill='#173947',outline='white',width=1)
        canvas.paste(m,(12,50));canvas.paste(Image.fromarray(rgb),(582,63))
        cd=ImageDraw.Draw(canvas);cd.text((16,10),'Fire  /  기록된 로봇 위치',font=font(25),fill=INK)
        cd.text((582,13),'로봇 카메라',font=font(23),fill=INK)
        cd.text((583,367),'관측 지점에서 A·B 방향으로 회전' if j==len(arr)-1 else '주행 중',font=font(21),fill=INK)
        gif.append(canvas)
    gif[0].save(out/'주행재생.gif',save_all=True,append_images=gif[1:],duration=[145]*(len(gif)-1)+[1700],loop=0,optimize=False)
if __name__=='__main__':main()
