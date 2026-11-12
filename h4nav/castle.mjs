// Simulation, teacher annotation and scoring. The policy worker receives only RGB and text.
import * as T from '../spatial/three.mjs';
import {floorHeight,directFloorLength,viewpointRange} from '../spatial/navmesh.mjs';
import {registeredGoals} from '../spatial/goals.mjs';
import {addIndoorGoals} from '../spatial/indoor-scene.mjs';
export const categories=['chair','bin','extinguisher'];
export const prompts=['chair','trash can','fire extinguisher'];
export const canonical=[[1.6,8.3],[1.4,18.3],[3.42,14.2]];
export const actions=['forward','left','right','stop'];
export async function castle(width=192,height=144){
  const spatial=new URL('../spatial/',import.meta.url);
  const floor=await (await fetch(new URL('floor.json',spatial))).json();
  const registry=registeredGoals(floor),world=new T.Scene(),overview=new T.Group();
  const loader=new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder);
  const {scene}=await loader.loadAsync(new URL('castle.glb',spatial).href);
  world.add(scene);
  const extinguisher=new T.Group(),members=[];
  scene.traverse(o=>{if(o.isMesh){
    const m=o.material;o.material=new T.MeshBasicMaterial({map:m.map,color:m.color,vertexColors:!!o.geometry.attributes.color,side:T.DoubleSide,alphaTest:m.alphaTest});
    if(o.name.startsWith('registered_C'))members.push(o);
  }});
  world.add(extinguisher);extinguisher.position.fromArray(floor.target);
  for(const o of members)extinguisher.attach(o);
  await addIndoorGoals(world,overview,registry);
  const objects=categories.map(k=>k==='extinguisher'?extinguisher:world.children.find(g=>g.isGroup&&g.getObjectByProperty('isMesh',true)?.userData.goal===k));
  if(objects.some(o=>!o)||!members.length)throw Error('Castle assets are incomplete');
  // The closed-loop evaluator sweeps the foot disk against the relocated
  // meshes. Measure each horizontal radius about its registered anchor.
  const vertex=new T.Vector3();
  const objectRadii=objects.map((group,k)=>{
    group.updateWorldMatrix(true,true);
    let radius=0;
    group.traverse(node=>{
      if(!node.isMesh)return;
      const position=node.geometry.attributes.position;
      for(let i=0;i<position.count;i++){
        vertex.fromBufferAttribute(position,i).applyMatrix4(node.matrixWorld);
        radius=Math.max(radius,Math.hypot(vertex.x-canonical[k][0],vertex.z-canonical[k][1]));
      }
    });
    return radius;
  });
  const origins=objects.map(o=>o.position.clone());
  objects.forEach((o,k)=>o.traverse(n=>{if(n.isMesh)n.userData.instance=k+1;}));
  const renderer=new T.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});renderer.setSize(width,height,false);
  const camera=new T.PerspectiveCamera(2*Math.atan(Math.tan(78*Math.PI/360)*height/width)*180/Math.PI,width/height,.02,100);
  const ctx=document.createElement('canvas').getContext('2d',{willReadFrequently:true});ctx.canvas.width=width;ctx.canvas.height=height;
  let anchors=[],present=[],isCanonical=false;
  const meshes=[];world.traverse(o=>{if(o.isMesh)meshes.push([o,o.material]);});
  const ids=[0x000000,0xff0000,0x00ff00,0x0000ff].map(c=>new T.MeshBasicMaterial({color:c,side:T.DoubleSide,toneMapped:false}));
  const elevation=(x,z)=>floorHeight(floor.tris,x,z);
  function place(points,removed=-1){
    anchors=points.map(p=>[...p]);present=points.map((_,i)=>i!==removed);
    isCanonical=points.every((p,i)=>Math.hypot(p[0]-canonical[i][0],p[1]-canonical[i][1])<1e-4);
    for(let i=0;i<3;i++){
      const [x,z]=points[i],[ox,oz]=canonical[i],base=origins[i];
      const y=elevation(x,z)??0,oy=elevation(ox,oz)??0;
      objects[i].position.set(base.x+x-ox,base.y+y-oy,base.z+z-oz);objects[i].visible=present[i];
    }
  }
  function render(p,mask=false){
    camera.position.set(p.x,(elevation(p.x,p.z)??0)+.46,p.z);camera.rotation.set(-.2,p.yaw,0,'YXZ');
    if(mask)for(const [o] of meshes)o.material=ids[o.userData.instance??0];
    renderer.render(world,camera);ctx.drawImage(renderer.domElement,0,0);
    if(mask)for(const [o,m] of meshes)o.material=m;
    return ctx.getImageData(0,0,width,height);
  }
  function labels(p){
    const data=render(p,true).data,stats=categories.map(()=>({pixels:0,box:[width,height,-1,-1]}));
    for(let i=0;i<data.length;i+=4){const c=data[i]>150?0:data[i+1]>150?1:data[i+2]>150?2:-1;
      if(c<0)continue;const s=stats[c],x=(i/4)%width,y=Math.floor(i/4/width),b=s.box;
      s.pixels++;b[0]=Math.min(b[0],x);b[1]=Math.min(b[1],y);b[2]=Math.max(b[2],x);b[3]=Math.max(b[3],y);}
    return stats;
  }
  function move(p,a){
    if(a===1||a===2){p.yaw+=(a===1?1:-1)*Math.PI/12;return true;}
    if(a!==0)return true;
    const x=p.x-.22*Math.sin(p.yaw),z=p.z-.22*Math.cos(p.yaw),y=elevation(x,z);
    if(y===null||!Number.isFinite(directFloorLength(floor.tris,[p.x,elevation(p.x,p.z),p.z],[x,y,z])))return false;
    if(anchors.some(([ax,az],i)=>present[i]&&Math.hypot(ax-x,az-z)<[.48,.44,.35][i]))return false;
    p.x=x;p.z=z;return true;
  }
  function score(p,k){
    const s=labels(p);
    if(k<0||!present[k])return {success:false,distance:null,visiblePixels:0,visible:s};
    const {pixels,box}=s[k],distance=Math.hypot(p.x-anchors[k][0],p.z-anchors[k][1]);
    const centered=pixels>0&&Math.abs((box[0]+box[2])/(2*width)-.5)<=.25;
    const view=isCanonical?viewpointRange(floor.tris,[p.x,elevation(p.x,p.z),p.z],registry[categories[k]].views):null;
    return {success:distance<=1.35&&centered&&pixels>=80,distance,centered,visiblePixels:pixels,visible:s,legacyView:view?.kind??null,viewDistance:view?.distance??null};
  }
  place(canonical);
  return {place,render,labels,move,score,objectRadii,elevation,floor,ctx,width,height,dispose(){renderer.dispose();renderer.forceContextLoss();}};
}
