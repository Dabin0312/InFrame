const sub=(a,b)=>a.map((v,i)=>v-b[i]), dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
export function ray(p,x,y,k){
  const u=(x-k.cx)/k.fx,v=(y-k.cy)/k.fy;
  const direction=[0,4,8].map(i=>p[i]*u+p[i+1]*v+p[i+2]);
  const length=Math.hypot(...direction);
  return {o:p.slice(12,15),d:direction.map(v=>v/length)};
}
function candidate(a,b){
  const c=dot(a.d,b.d), den=1-c*c;
  if(c<0.5||den<0.0012)return null;
  const between=sub(b.o,a.o),u=dot(between,a.d),v=dot(between,b.d);
  const s=(u-c*v)/den,t=(c*u-v)/den;
  if(s<=0||t<=0)return null;
  return a.o.map((q,i)=>(q+s*a.d[i]+b.o[i]+t*b.d[i])/2);
}
function error(p,r){
  const v=sub(p,r.o),n=Math.hypot(...v);
  return n>0?Math.acos(Math.max(-1,Math.min(1,dot(v,r.d)/n))):Math.PI;
}
export function triangulate(rays, limit=.017){
  if(rays.length<2)return null;
  let best=null,loss=Infinity;
  for(let i=1;i<rays.length;i++){
    const p=candidate(rays[0],rays[i]);if(!p)continue;
    const errors=rays.map(r=>error(p,r)).sort((a,b)=>a-b);
    const score=errors[Math.min(errors.length-1,Math.floor(errors.length*.8))];
    if(score<limit && score<loss){best=p;loss=score;}
  }
  return best;
}
export class Targets{
  tracks=[];serial=0;
  update(boxes,pose,k,t,seg){
    const used=new Set();
    for(const b of boxes){
      const [x,y,w,h]=b.box,cx=x+w/2,cy=y+h/2;
      let match=null,dist=Infinity;
      for(const tr of this.tracks){
        if(tr.seg!==seg||used.has(tr.id)||t-tr.last>1.05)continue;
        const d=Math.hypot((cx-tr.cx)/Math.max(w,tr.w,9),(cy-tr.cy)/Math.max(h,tr.h,9));
        if(d<.9&&d<dist){dist=d;match=tr;}
      }
      if(!match){match={id:++this.serial,seg,rays:[],times:[],p:null};this.tracks.push(match);}
      Object.assign(match,{cx,cy,w,h,last:t});used.add(match.id);match.times.push(t);b.track=match.id;
      if(pose){
        const r=ray(pose,cx,cy,k);match.rays.push(r);
        if(match.rays.length>28)match.rays.splice(1,1);
        if(match.rays.length>=3)match.p=triangulate(match.rays,.026)||match.p;
      }
    }
  }
}
