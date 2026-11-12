import {floorHeight} from './navmesh.mjs';
import {goals} from './goals.mjs';

// All four soles of the animated Go2 fit inside this disk at every yaw.
export const footRadius = .38;
const cached = new WeakMap();
function segmentDistance(x,z,a,b) {
  const dx=b[0]-a[0],dz=b[2]-a[2];
  const t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[2])*dz)/(dx*dx+dz*dz||1)));
  return Math.hypot(x-a[0]-t*dx,z-a[2]-t*dz);
}
export function footprint(floor){
  if(cached.has(floor))return cached.get(floor);
  const edges=new Map();
  for(const tri of floor.tris)for(let i=0;i<3;i++){
    const a=tri[i],b=tri[(i+1)%3],key=[a.join(','),b.join(',')].sort().join('|');
    if(edges.has(key))edges.delete(key);else edges.set(key,[a,b]);
  }
  const boundary=[...edges.values()],objects=Object.values(goals).filter(g=>g.xz);
  function clearance(x,z) {
    if(floorHeight(floor.tris,x,z)===null)return -Infinity;
    let d=Infinity;
    for(const [a,b] of boundary)d=Math.min(d,segmentDistance(x,z,a,b));
    for(const g of objects)d=Math.min(d,Math.hypot(x-g.xz[0],z-g.xz[1])-g.radius);
    return d;
  }
  function clear(a,b,margin=0){
    // Clearance is 1-Lipschitz. The midpoint of each interval must have space
    // for the whole foot disk plus half the interval, including curved corners.
    const length=Math.hypot(a[0]-b[0],a[2]-b[2]);
    const n=Math.max(1,Math.ceil(length/.075));
    for(let i=0;i<n;i++){
      const t=(i+.5)/n;
      if(clearance(a[0]+t*(b[0]-a[0]),a[2]+t*(b[2]-a[2]))<footRadius+margin+length/(2*n))return false;
    }
    return true;
  }
  const shape={boundary,clearance,clear,fits:(x,z)=>clearance(x,z)>=footRadius};
  cached.set(floor,shape);
  return shape;
}
