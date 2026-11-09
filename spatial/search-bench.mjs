import * as T from './three.mjs';
import {openDetector} from './open-detector.mjs';
import {searchPolicy} from './search-policy.mjs';
const W=320,H=240,cache=new Map();
const stations=[[-2,0],[0,0],[2,0],[2,1.65],[2,0],[0,0],[-2,0],[-2,-1.65]];
const blocks=[[-4.1,0,.2,6.4],[4.1,0,.2,6.4],[0,-3.1,8.4,.2],[0,3.1,8.4,.2],[0,-2,.18,2.1],[0,2,.18,2.1]];
function addCone(scene,placement,height=0){
  const mat=color=>new T.MeshStandardMaterial({color,roughness:.86});
  let target=null;
  if(placement){
    target=new T.Group();const base=new T.Mesh(new T.BoxGeometry(.44,.065,.44),mat(0xf35a0a));base.position.y=.035;target.add(base);
    const bounds=[.06,.24,.34,.45,.54,.65],colors=[0xff5806,0xfff9de,0xff5806,0xfff9de,0xff5806];
    const radius=y=>.19-(y-.06)*.27;
    for(let j=0;j<colors.length;j++){const a=bounds[j],b=bounds[j+1];const cone=new T.Mesh(new T.CylinderGeometry(radius(b),radius(a),b-a,40),mat(colors[j]));cone.position.y=(a+b)/2;target.add(cone);}
    target.position.set(placement[0],height,placement[1]);scene.add(target);
  }
  return target;
}
async function castle(placement){
  const [{floorHeight},floor,gltf]=await Promise.all([import('./navmesh.mjs'),fetch(new URL('floor.json',import.meta.url)).then(r=>r.json()),new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder).loadAsync(new URL('castle.glb',import.meta.url).href)]);
  const scene=new T.Scene();scene.add(gltf.scene);
  gltf.scene.traverse(o=>{if(o.isMesh){const m=o.material;o.material=new T.MeshBasicMaterial({map:m.map,color:m.color,vertexColors:!!o.geometry.attributes.color,side:T.DoubleSide,alphaTest:m.alphaTest});}});
  scene.add(new T.HemisphereLight(0xffffff,0xa7a195,2.7));
  const y=(x,z)=>floorHeight(floor.tris,x,z);
  const target=addCone(scene,placement,placement?y(...placement):0);
  const ok=(x,z)=>x>=0&&x<=4.5&&z>=7&&z<=12&&y(x,z)!==null&&(!placement||Math.hypot(x-placement[0],z-placement[1])>.39);
  return {scene,target,ok,y,waypoints:[[2,9],[.6,9],[.6,11],[3.6,11],[3.6,7.8],[2,7.8]]};
}
function lab(placement){
  const scene=new T.Scene();scene.background=new T.Color(0xe7e5df);
  const mat=(color)=>new T.MeshStandardMaterial({color,roughness:.86});
  function box(x,y,z,w,h,d,color){
    const m=new T.Mesh(new T.BoxGeometry(w,h,d),mat(color));m.position.set(x,y,z);scene.add(m);return m;
  }
  box(0,-.07,0,8.4,.14,6.4,0xc2bbb1);
  for(const [x,z,w,d] of blocks){box(x,1.3,z,w,2.6,d,0xd4ded9);box(x,.08,z,w+.02,.16,d+.02,0x798e85);}
  const grid=new T.GridHelper(8,16,0xb4aa9a,0xb4aa9a);grid.position.y=.001;scene.add(grid);
  // A warm-coloured rectangular distractor is present in every episode.
  box(3.85,.36,.15,.23,.72,.52,0xe19249);
  scene.add(new T.HemisphereLight(0xffffff,0x9e9182,2));
  const light=new T.DirectionalLight(0xfff6dc,2.2);light.position.set(-2,5,2);scene.add(light);
  const target=addCone(scene,placement);
  const ok=(x,z)=>blocks.every(([a,b,w,h])=>Math.abs(x-a)>w/2+.18||Math.abs(z-b)>h/2+.18)&&(!placement||Math.hypot(x-placement[0],z-placement[1])>.39);
  return {scene,target,ok};
}
export async function runSearch({prompt,start,placement,environment='rooms',maxSteps=180},onStep=()=>{}){
  if(!cache.has(prompt)){
    for(const previous of cache.values())await (await previous).release();
    cache.clear();
    cache.set(prompt,openDetector(prompt,W,H).catch(error=>{cache.delete(prompt);throw error;}));
  }
  const detect=await cache.get(prompt);
  const {scene,target,ok,y=()=>0,waypoints=stations}=environment==='castle'?await castle(placement):lab(placement);
  const renderer=new T.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
  renderer.setSize(W,H,false);
  const cam=new T.PerspectiveCamera(2*Math.atan(Math.tan(68*Math.PI/360)*H/W)*180/Math.PI,W/H,.03,25);
  const ctx=document.createElement('canvas').getContext('2d',{willReadFrequently:true});ctx.canvas.width=W;ctx.canvas.height=H;
  const p={x:start[0],z:start[1],yaw:start[2]},step=searchPolicy(waypoints),trace=[];
  let end='budget_exhausted',bumps=0,photo,matched=false,distance=null,seen=false,blocked=false;
  try{
    for(let n=0;n<maxSteps;n++){
      cam.position.set(p.x,y(p.x,p.z)+.52,p.z);cam.rotation.set(-.11,p.yaw,0,'YXZ');renderer.render(scene,cam);
      ctx.drawImage(renderer.domElement,0,0);const boxes=await detect(ctx.getImageData(0,0,W,H).data);
      const a=step(p,boxes,blocked);blocked=false;trace.push({...p,action:a.type,boxes:boxes.map(({box,score})=>({box,score}))});
      seen||=boxes.some(b=>b.score>=.36);onStep(ctx.canvas,p,a,n);
      if(a.type==='goal_stop'||a.type==='search_exhausted'||n===maxSteps-1){
        if(a.type==='goal_stop'||a.type==='search_exhausted')end=a.type;
        // Independent evaluation after the action. Raycast the chosen RGB box through the rendered scene.
        if(target){
          distance=Math.hypot(p.x-target.position.x,p.z-target.position.z);
          if(boxes.length){const [x,y,w,h]=boxes[0].box;const ray=new T.Raycaster();ray.setFromCamera(new T.Vector2((x+w/2)/W*2-1,1-(y+h/2)/H*2),cam);
            const hit=ray.intersectObjects(scene.children.filter(o=>!o.isLineSegments),true)[0]?.object;matched=!!hit&&target.children.includes(hit);}
        }
        if(end==='goal_stop'&&boxes.length){const [x,y,w,h]=boxes[0].box;ctx.strokeStyle='#00f3c5';ctx.lineWidth=2;ctx.strokeRect(x,y,w,h);}
        photo=ctx.canvas.toDataURL('image/jpeg',.90);break;
      }
      if(a.type==='turn')p.yaw=a.yaw;
      if(a.type==='forward'){
        const x=p.x-Math.sin(p.yaw)*a.metres,z=p.z-Math.cos(p.yaw)*a.metres;
        if(ok(x,z)&&ok((x+p.x)/2,(z+p.z)/2)){p.x=x;p.z=z;}else{bumps++;blocked=true;}
      }
    }
    return {prompt,start,placement,environment,end,seen,bumps,matched,distance,trace,photo};
  }finally{
    scene.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});renderer.dispose();renderer.forceContextLoss();
  }
}
