// Register the suite before training. Only the geometry sampler sees the floor.
import fs from 'node:fs';
import {floorHeight} from '../spatial/navmesh.mjs';
const {tris}=JSON.parse(fs.readFileSync(new URL('../spatial/floor.json',import.meta.url)));
const suite=process.argv[3]??'bin';
if(!['bin','panel'].includes(suite)) throw Error('Expected bin or panel suite');
const seed=suite==='panel'?78041657:41821099;
const groupSize=suite==='panel'?4:8;
let state=seed;
const random=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
const round=v=>+v.toFixed(4);
function free(x,z){
 return [[0,0],[.16,0],[-.16,0],[0,.16],[0,-.16]].every(([dx,dz])=>floorHeight(tris,x+dx,z+dz)!==null);
}
function point(){
 for(;;){const x=round(-3.1+10.4*random()),z=round(5.8+16.3*random());if(free(x,z))return [x,z];}
}
const layouts={};
for(let i=1;i<=24;i++){
 let start;
 const group=i<=groupSize?'gallery':i<=2*groupSize?'perimeter':'panel';
 if(group==='gallery'){
   const [x,z]=point();start={x,z,yaw:round((2*random()-1)*Math.PI)};
 }else if(group==='perimeter'){
   for(;;){const [x,z]=point(),yaw=(random()*2-1)*Math.PI;
     if(floorHeight(tris,x-1.70*Math.sin(yaw),z-1.70*Math.cos(yaw))===null){start={x,z,yaw:round(yaw)};break;}}
 }else{
   for(;;){const x=round(5.15+1.38*random()),z=round(7.5+3.35*random());
     if(free(x,z)){start={x,z,yaw:round(-Math.PI/2+(random()*2-1)*1.15)};break;}}
 }
 const anchors=[];
 while(anchors.length<3){
   const p=point(),d=Math.hypot(p[0]-start.x,p[1]-start.z);
   if(d>=2.0&&d<=7&&anchors.every(q=>Math.hypot(p[0]-q[0],p[1]-q[1])>=1.35))anchors.push(p);
 }
 layouts[suite+i]={group,start,anchors};
}
fs.writeFileSync(process.argv[2],JSON.stringify({seed,stepLimit:120,layouts},null,2)+'\n');
