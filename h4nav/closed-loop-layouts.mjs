// Preflight uses geometry and target ID masks only to certify that the task is
// solvable. No decision model is loaded while the held-out suite is generated.
import {castle} from './castle.mjs';
import {footprint,footRadius} from '../spatial/footprint.mjs';
import {directFloorLength} from '../spatial/navmesh.mjs';
import {placements} from './closed-loop-world.mjs';

function generator(seed){
  let n=seed;
  return ()=>{n=(Math.imul(n,1664525)+1013904223)>>>0;return n/4294967296;};
}
const separation=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
export async function makeSuite(){
  const seed=1635784017,random=generator(seed),sim=await castle(160,120);
  const base=footprint(sim.floor,[]),round=n=>+n.toFixed(5);
  const grid=.3,knownEdges=new Map();
  const xyz=([x,z])=>[x,sim.elevation(x,z),z];
  function baseClear(a,b){
    const key=[a.join(),b.join()].sort().join('|');
    if(!knownEdges.has(key)){
      const p=xyz(a),q=xyz(b);
      knownEdges.set(key,p[1]!==null&&q[1]!==null&&base.clear(p,q)&&Number.isFinite(directFloorLength(sim.floor.tris,p,q)));
    }
    return knownEdges.get(key);
  }
  function certificates(start,anchors){
    const objects=placements(sim,anchors,-1);
    function allowed(a,b){
      const dx=b[0]-a[0],dz=b[1]-a[1],d=dx*dx+dz*dz;
      return objects.every(({xz,radius})=>{
        const t=d?Math.max(0,Math.min(1,((xz[0]-a[0])*dx+(xz[1]-a[1])*dz)/d)):0;
        return separation([a[0]+t*dx,a[1]+t*dz],xz)>radius+footRadius;
      })&&baseClear(a,b);
    }
    const point=(i,j)=>[round(i*grid),round(j*grid)];
    const origin=[start.x,start.z],ix=Math.round(start.x/grid),iz=Math.round(start.z/grid);
    const todo=[],seen=new Set(),views=[null,null,null];
    function add(i,j,parent){
      const k=i+','+j;
      if(seen.has(k)||!allowed(parent,point(i,j)))return;
      seen.add(k);todo.push([i,j]);
    }
    for(let i=ix-1;i<=ix+1;i++)for(let j=iz-1;j<=iz+1;j++)add(i,j,origin);
    for(let h=0;h<todo.length;h++){
      const [i,j]=todo[h],q=point(i,j);
      for(const [k,a] of anchors.entries()){
        const d=separation(q,a);
        if(views[k]||d<.90||d>1.20)continue;
        const pose={x:q[0],z:q[1],yaw:Math.atan2(q[0]-a[0],q[1]-a[1])};
        const score=sim.score(pose,k);
        if(score.success)views[k]={pose,distance:score.distance,visiblePixels:score.visiblePixels};
      }
      if(views.every(Boolean))return views;
      for(const [di,dj] of [[0,1],[0,-1],[1,0],[-1,0]])add(i+di,j+dj,q);
    }
    return null;
  }
  const layouts=[];let attempts=0;
  try{
    while(layouts.length<12 && ++attempts<=3000){
      const zone=layouts.length%3;
      const [lo,hi]=[[7,11.5],[12,16.5],[17,21.5]][zone];
      const origin=[round(-3.9+random()*9.8),round(lo+random()*(hi-lo))];
      if(base.clearance(...origin)<.62||layouts.some(l=>separation(origin,[l.start.x,l.start.z])<.9))continue;
      const start={x:origin[0],z:origin[1],yaw:round((random()*2-1)*Math.PI)};
      const anchors=[];
      for(let i=0;i<125&&anchors.length<3;i++){
        const r=2.4+random()*4.1,a=random()*2*Math.PI;
        const q=[round(origin[0]+r*Math.cos(a)),round(origin[1]+r*Math.sin(a))];
        if(q[1]<4||q[1]>24||base.clearance(...q)<sim.objectRadii[anchors.length]+.12||
           anchors.some(p=>separation(q,p)<1.7))continue;
        anchors.push(q);
      }
      if(anchors.length!==3)continue;
      sim.place(anchors);
      const views=certificates(start,anchors);
      if(views)layouts.push({id:'C'+String(layouts.length+1).padStart(2,'0'),zone,start,anchors,views});
    }
    if(layouts.length!==12)throw Error('Cannot fill preflight suite');
    return {seed,stepLimit:240,period:.25,goals:['chair','trash can','fire extinguisher'],
      policySHA256:'184620618c098203cf8de7c2d1060e203a0703f09ee4dddec535d8860cac6851',
      scoring:{maxDistance:1.35,minMaskPixels:80,maxHorizontalOffset:.25},objectRadii:sim.objectRadii,footRadius,attempts,layouts};
  }finally{sim.dispose();}
}
