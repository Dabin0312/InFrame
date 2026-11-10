// Register eight paired tests using only walkable geometry and an independent seed.
import fs from 'node:fs';
import {floorHeight} from '../spatial/navmesh.mjs';
const {tris}=JSON.parse(fs.readFileSync(new URL('../spatial/floor.json',import.meta.url)));
const seed=650727083;
let state=seed;
const rnd=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
function sample(){
  for(;;){
    const p=[-2.7+9.1*rnd(),6.4+15.3*rnd()].map(x=>+x.toFixed(3));
    if([[0,0],[-.15,0],[.15,0],[0,-.15],[0,.15]].every(([dx,dz])=>floorHeight(tris,p[0]+dx,p[1]+dz)!==null))return p;
  }
}
const layouts={};
for(let i=1;i<=8;i++){
 const origin=sample(),anchors=[];
 while(anchors.length<3){
   const p=sample(),d=Math.hypot(origin[0]-p[0],origin[1]-p[1]);
   if(d>=2.2&&d<=7&&anchors.every(q=>Math.hypot(q[0]-p[0],q[1]-p[1])>=1.3))anchors.push(p);
 }
 layouts['blind'+i]={start:{x:origin[0],z:origin[1],yaw:+((rnd()*2-1)*Math.PI).toFixed(5)},anchors};
}
fs.writeFileSync(process.argv[2],JSON.stringify({seed,stepLimit:120,layouts},null,2)+'\n');
