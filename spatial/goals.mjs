import {floorHeight} from './navmesh.mjs';
export const goals={
  extinguisher:{label:'소화기',prompt:'fire extinguisher',prefix:'E',asset:'extinguisher.onnx',channel:0,id:'C'},
  chair:{label:'의자',prompt:'chair',prefix:'H',asset:'indoor.onnx',channel:0,id:'H',mesh:'chair.glb',xz:[1.6,8.3],view:[2.9,9.0],height:.86,radius:.75,yaw:.9},
  bin:{label:'쓰레기통',prompt:'trash can',prefix:'B',asset:'indoor.onnx',channel:1,id:'B',mesh:'bin.glb',xz:[1.4,18.3],view:[2.35,17.3],height:.76,radius:.70,yaw:1.1}
};

// Three consecutive eligible boxes on the same track at 4 Hz. The stop rule
// uses only the selected class, screen position, apparent size and persistence.
export class VisualStop {
  constructor(){this.counts=new Map();this.last=-Infinity;this.seg=null;}
  step(boxes,width,height,time,segment){
    if(this.seg!==segment||Math.abs(time-this.last-.25)>.001)this.counts.clear();
    const next=new Map();let chosen=null;
    for(const b of boxes){
      const [x,,w,h]=b.box,cx=(x+w/2)/width;
      if(b.score<.36||h/height<.19||w/width<.045||Math.abs(cx-.5)>.30)continue;
      const n=(this.counts.get(b.track)||0)+1;next.set(b.track,n);
      if(n>=3&&(!chosen||b.score>chosen.score))chosen=b;
    }
    this.counts=next;this.last=time;this.seg=segment;return chosen;
  }
}

export function registeredGoals(floor){
  const surface=([x,z])=>[x,floorHeight(floor.tris,x,z),z];
  return Object.fromEntries(Object.entries(goals).map(([key,g])=>[key,{
    ...g,xyz:g.xz?surface(g.xz):floor.target,views:g.view?[surface(g.view)]:floor.views
  }]));
}
export function occupied(x,z){
  return crossesObject(x,z,x,z);
}

// Robot-centre clearance covers the object's footprint plus the NavMesh agent radius.
export function crossesObject(ax,az,bx,bz){
  const dx=bx-ax,dz=bz-az,length=dx*dx+dz*dz;
  return Object.values(goals).some(g=>{
    if(!g.xz)return false;
    const t=length?Math.max(0,Math.min(1,((g.xz[0]-ax)*dx+(g.xz[1]-az)*dz)/length)):0;
    return Math.hypot(ax+t*dx-g.xz[0],az+t*dz-g.xz[1])<g.radius;
  });
}
