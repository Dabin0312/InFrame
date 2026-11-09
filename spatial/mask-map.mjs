import {ray,triangulate} from './geometry.mjs';
const side=24;
function margins(mask){
  // Distance to the mask boundary, in cells of the normalized instance crop.
  const d=Float32Array.from(mask,x=>x?side:0);
  for(let y=0;y<side;y++)for(let x=0;x<side;x++){
    const i=y*side+x;d[i]=Math.min(d[i],1+(x?d[i-1]:0),1+(y?d[i-side]:0));
  }
  for(let y=side-1;y>=0;y--)for(let x=side-1;x>=0;x--){
    const i=y*side+x;d[i]=Math.min(d[i],1+(x<side-1?d[i+1]:0),1+(y<side-1?d[i+side]:0));
  }
  return d;
}
export function maskView(pose,k,b,t){return {pose,k,box:b.box,d:margins(b.mask),t};}
function margin(v,point){
  const {pose:p,k,box:[x,y,w,h]}=v;
  const dx=point[0]-p[12],dy=point[1]-p[13],dz=point[2]-p[14];
  const z=p[2]*dx+p[6]*dy+p[10]*dz;if(z<=0)return 0;
  const mx=Math.floor(side*((k.fx*(p[0]*dx+p[4]*dy+p[8]*dz)/z+k.cx)-x)/w);
  const my=Math.floor(side*((k.fy*(p[1]*dx+p[5]*dy+p[9]*dz)/z+k.cy)-y)/h);
  return mx<0||my<0||mx>=side||my>=side?0:v.d[my*side+mx];
}
export function confirmedAnchor(views){
  if(views.length<4)return null;
  // Fit earlier views, then independently check the newest silhouette.
  const fit=views.slice(0,-1),ref=fit[0],last=views.at(-1);
  const centre=v=>ray(v.pose,v.box[0]+v.box[2]/2,v.box[1]+v.box[3]/2,v.k);
  const a=centre(ref),seeds=[];
  for(const v of fit.slice(1)){
    const b=centre(v),p=triangulate([a,b],.065);
    if(p)seeds.push(Math.hypot(...p.map((s,i)=>s-a.o[i])));
  }
  if(!seeds.length)return null;
  const depth=seeds.sort((a,b)=>a-b)[Math.floor(seeds.length/2)];
  if(Math.hypot(...a.o.map((s,i)=>s-last.pose[12+i]))/depth<.025)return null;
  let score=0,best=null;
  const [x,y,w,h]=ref.box;
  for(let r=2;r<side;r+=3)for(let c=2;c<side;c+=3){
    if(ref.d[r*side+c]<2)continue;
    const line=ray(ref.pose,x+(c+.5)*w/side,y+(r+.5)*h/side,ref.k);
    for(let j=-8;j<=8;j++){
      const dist=depth*Math.exp(j*.09),p=line.o.map((s,i)=>s+line.d[i]*dist);
      const values=fit.map(v=>margin(v,p)),min=Math.min(...values);
      if(min<1)continue;
      const s=min+.1*values.reduce((a,b)=>a+b,0)/values.length;
      if(s>score){best=p;score=s;}
    }
  }
  return best&&margin(last,best)>=1?best:null;
}
