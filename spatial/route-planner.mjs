import {footprint} from './footprint.mjs';
import {floorHeight} from './navmesh.mjs';
import {occupied,crossesObject} from './goals.mjs';

const step=.25, directions=[[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[2]-b[2]);
export function buildPlanner(floor){
  const support=footprint(floor);
  const nodes=[],index=new Map();
  const vertices=floor.tris.flat();
  const bounds=k=>[Math.ceil(Math.min(...vertices.map(v=>v[k]))/step),Math.floor(Math.max(...vertices.map(v=>v[k]))/step)];
  const [xmin,xmax]=bounds(0),[zmin,zmax]=bounds(2);
  function walkable(x,z){return !occupied(x,z)&&floorHeight(floor.tris,x,z)!==null;}
  function clear(a,b){
    if(!support.clear(a,b)||crossesObject(a[0],a[2],b[0],b[2]))return false;
    const n=Math.max(1,Math.ceil(dist(a,b)/.055));
    for(let i=1;i<=n;i++){const t=i/n;if(!walkable(a[0]+(b[0]-a[0])*t,a[2]+(b[2]-a[2])*t))return false;}
    return true;
  }
  for(let x=xmin;x<=xmax;x++)for(let z=zmin;z<=zmax;z++){
    const xx=x*step,zz=z*step,y=floorHeight(floor.tris,xx,zz);
    if(y===null||!support.fits(xx,zz))continue;
    index.set(x+','+z,nodes.length);nodes.push({p:[xx,y,zz],x,z});
  }
  function nearest(point){
    const candidates=nodes.map((n,i)=>[dist(point,n.p),i]).filter(([d])=>d<=.8).sort((a,b)=>a[0]-b[0]);
    return candidates.find(([,i])=>clear(point,nodes[i].p))?.[1];
  }
  function route(start,dest){
    if(clear(start,dest))return [dest];
    const a=nearest(start),b=nearest(dest);
    if(a===undefined||b===undefined)return null;
    const open=new Set([a]),prior=new Map(),cost=new Map([[a,0]]);
    while(open.size){
      let best,score=Infinity;
      for(const i of open){const f=cost.get(i)+dist(nodes[i].p,nodes[b].p);if(f<score){score=f;best=i;}}
      if(best===b){
        const path=[dest];let i=b;
        while(i!==undefined){path.unshift(nodes[i].p);i=prior.get(i);}
        const compact=[];let from=start;
        for(let k=0;k<path.length;){let j=path.length-1;while(j>k&&!clear(from,path[j]))j--;from=path[j];compact.push(from);k=j+1;}
        return compact;
      }
      open.delete(best);const n=nodes[best];
      for(const [dx,dz] of directions){
        const j=index.get((n.x+dx)+','+(n.z+dz));if(j===undefined)continue;
        const next=cost.get(best)+step*Math.hypot(dx,dz);
        if((cost.get(j)??Infinity)<=next||!clear(n.p,nodes[j].p))continue;
        cost.set(j,next);prior.set(j,best);open.add(j);
      }
    }
    return null;
  }
  return (start,views)=>{
    const choices=[...views].sort((a,b)=>dist(start,a)-dist(start,b));
    for(const v of choices){const path=route(start,v);if(path)return path;}
    return null;
  };
}
export function followRoute(path,pose,yaw,goal,visualMatch){
  while(path.length>1&&dist(pose,path[0])<.045)path.shift();
  const waypoint=path[0],remaining=dist(pose,waypoint);
  const approach=path.length===1&&remaining<.18;
  const destination=approach?goal.xyz:waypoint;
  const desired=Math.atan2(pose[0]-destination[0],pose[2]-destination[2]);
  const turn=Math.atan2(Math.sin(desired-yaw),Math.cos(desired-yaw));
  if(approach&&Math.abs(turn)<.18&&visualMatch)return [0,0,1];
  return [approach||Math.abs(turn)>.10?0:Math.min(.65,remaining*2),Math.max(-1.6,Math.min(1.6,turn*3)),0];
}
