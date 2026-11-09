// Browser port of the frozen recovery controller. All angles are in radians.
const clip=(x,min,max)=>Math.max(min,Math.min(max,x));
const rad=(d)=>d*Math.PI/180;
const offsets=[-90,-60,-45,-30,-15,0,15,30,45,60,90].map(rad);
const clearance=(corr)=>Array.from(corr.slice(3),x=>.72/(1+Math.exp(-clip(x,-18,18))));
const remaining=(base)=>Math.expm1(clip(base[2],0,4));
function atAngle(angle,ranges){
  let k=1;while(k<offsets.length-1 && offsets[k]<angle)k++;
  return ranges[k-1]+(ranges[k]-ranges[k-1])*(angle-offsets[k-1])/(offsets[k]-offsets[k-1]);
}
function steer(base,corr,ranges,cfg){
  const distance=remaining(base), yaw=Math.atan2(base[0],base[1]);
  if(base[3]>=0 && distance<=.65)return [0,0,1];
  const front=atAngle(clip(1.8*yaw,-1,1)*.125,ranges);
  const risk=clip((cfg.guard+.20-front)/.30,0,1);
  const w=(cfg.blend+(.66-cfg.blend)*risk)*clip((distance-.5)/.65,0,1);
  const expert=Math.atan2(corr[0],corr[1]);
  let desired=Math.atan2((1-w)*Math.sin(yaw)+w*Math.sin(expert),(1-w)*Math.cos(yaw)+w*Math.cos(expert));
  if(Math.abs(desired)>rad(cfg.behind))return [0,1,0];
  if(front<cfg.guard && Math.abs(desired)<rad(80)){
    const q=offsets.map((a,i)=>Math.cos(a-desired)+1.65*Math.min(ranges[i]/.55,1));
    const i=q.indexOf(Math.max(...q));if(ranges[i]<.23)return [0,1,0];
    desired=offsets[i];
  }
  const omega=clip(1.8*desired,-1,1);
  if(Math.abs(desired)>=rad(48)||front<.10)return [0,Math.abs(omega)<.2?1:omega,0];
  return [Math.min(clip(distance/.25,.14,.4)*Math.max(0,Math.cos(desired)),Math.max(.04,(front-.075)/.25)),omega,0];
}

// Same 4:3, antialiased bilinear downsample as policy.resize (192×144 → 80×60).
function filterWeights(src,dst){
  const scale=src/dst;
  return Array.from({length:dst},(_,j)=>{
    const c=(j+.5)*scale-.5, a=Math.max(0,Math.ceil(c-scale)), b=Math.min(src-1,Math.floor(c+scale));
    const w=Array.from({length:b-a+1},(_,i)=>Math.max(0,1-Math.abs(a+i-c)/scale));
    const sum=w.reduce((x,y)=>x+y,0);return w.map((v,i)=>[a+i,v/sum]);
  });
}
const wx=filterWeights(192,80),wy=filterWeights(144,60);
export function reduceRGB(rgba){
  const tmp=new Uint8Array(144*80*3),out=new Uint8Array(60*80*3);
  for(let y=0;y<144;y++)for(let x=0;x<80;x++)for(let ch=0;ch<3;ch++){
    let a=0;for(const [i,w] of wx[x])a+=rgba[(y*192+i)*4+ch]*w;
    tmp[(y*80+x)*3+ch]=Math.round(a);
  }
  for(let y=0;y<60;y++)for(let x=0;x<80;x++)for(let ch=0;ch<3;ch++){
    let a=0;for(const [i,w] of wy[y])a+=tmp[(i*80+x)*3+ch]*w;
    out[(y*80+x)*3+ch]=Math.round(a);
  }
  return out;
}
function gray(rgb){
  const out=new Float32Array(4800);
  for(let i=0;i<4800;i++)out[i]=Math.round((4899*rgb[3*i]+9617*rgb[3*i+1]+1868*rgb[3*i+2])/16384);
  return out;
}
function motionError(prev,curr,angle){
  const f=40/Math.tan(rad(39)),c=Math.cos(angle),s=Math.sin(angle),p=Math.cos(-.2),q=Math.sin(-.2);
  const a=gray(prev),b=gray(curr),diff=new Float32Array(4800),valid=new Uint8Array(4800);
  for(let y=0;y<60;y++)for(let x=0;x<80;x++){
    const i=y*80+x,h=(x-39.5)/f,v=(29.5-y)/f, py=p*v+q,pz=q*v-p;
    const rx=c*h+s*pz,rz=-s*h+c*pz, ry=p*py+q*rz, depth=q*py-p*rz;
    const u=39.5+f*rx/depth,t=29.5-f*ry/depth;
    valid[i]=u>2&&u<77&&t>2&&t<57&&y>17;
    const ux=Math.round(u*32)/32,ty=Math.round(t*32)/32,l=Math.floor(ux),k=Math.floor(ty);
    let value=0;
    for(let yy=k;yy<=k+1;yy++)for(let xx=l;xx<=l+1;xx++)
      if(xx>=0&&xx<80&&yy>=0&&yy<60)value+=a[yy*80+xx]*(1-Math.abs(xx-ux))*(1-Math.abs(yy-ty));
    diff[i]=value-b[i];
  }
  const reflect=(i,n)=>i<0?-i:i>=n?2*n-2-i:i;
  const e=Math.exp(-1/(2*.8*.8)), kernel=[e/(1+2*e),1/(1+2*e),e/(1+2*e)];
  let total=0,count=0;
  for(let y=0;y<60;y++)for(let x=0;x<80;x++)if(valid[y*80+x]){
    let v=0;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)
      v+=kernel[dy+1]*kernel[dx+1]*diff[reflect(y+dy,60)*80+reflect(x+dx,80)];
    total+=Math.abs(v);count++;
  }
  return count?total/count:Infinity;
}
export class Controller{
  constructor(config){this.config=config;this.recent=[];this.turn=0;this.progress=0;this.sign=1;this.previous=null;}
  step(base,corr,dock,image){
    const ranges=clearance(corr), proposal=steer(base,corr,ranges,this.config);
    const recent=this.recent, prior=recent.at(-1);
    const blocked=prior && prior[0]>.14 && motionError(this.previous,image,prior[1]*.25)<1.6;
    const decide=()=>{
      if(proposal[2])return proposal;
      if(dock[0]>1 && dock[1]>.9)return [0,0,1];
      if(dock[0]>1.2){
        let a=Math.atan2(dock[2],dock[3]);if(Math.abs(a)>.20){
          if(Math.abs(a)>2.35)a=Math.abs(a);return [0,clip(1.8*a,-1,1),0];
        }
      }
      const angles=[...recent.map(a=>a[1]),proposal[1]];
      const toggling=angles.length===4 && angles.every(a=>Math.abs(a)>.60) &&
        angles.slice(1).every((a,i)=>a*angles[i]<0) && recent.every(a=>a[0]<.03);
      if(blocked || (toggling&&!this.turn&&!this.progress)){
        const delta=(ranges[8]+ranges[9]+ranges[10]-ranges[0]-ranges[1]-ranges[2])/3;
        this.sign=Math.abs(delta)>.10?Math.sign(delta):corr[0]>=0?1:-1;
        this.turn=blocked?7:6;this.progress=blocked?4:2;
      }
      if(this.turn>0){this.turn--;return [0,this.sign,0];}
      if(this.progress>0){this.progress--;if(ranges[5]>.24)return [.28,0,0];}
      return proposal;
    };
    const action=decide();recent.push(action);if(recent.length>3)recent.shift();this.previous=image;return action;
  }
}
