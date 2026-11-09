import {floorHeight,viewpointRange} from './navmesh.mjs';
import * as T from './three.mjs';
import {ask} from './rpc.mjs';
const $=s=>document.querySelector(s);
const dt=.25;
async function model(){
  const loader=new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder);
  const gltf=await loader.loadAsync(new URL('go2.glb',import.meta.url).href);
  const body=new T.Group(),basis=new T.Group(),legs=[];
  basis.quaternion.setFromRotationMatrix(new T.Matrix4().set(0,-1,0,0,0,0,1,0,-1,0,0,0,0,0,0,1));
  basis.add(gltf.scene);body.add(basis);gltf.scene.getObjectByName('base').position.z=.305;
  for(const name of ['FL','FR','RL','RR']){
    const hip=gltf.scene.getObjectByName(name+'_thigh'),knee=gltf.scene.getObjectByName(name+'_calf');
    hip.rotation.y=.79;knee.rotation.y=-1.54;legs.push({hip,knee,phase:['FL','RR'].includes(name)?1:-1});
  }
  return {body,legs};
}
export async function init(floor, getStart, onPose){
  const canvas=$('#orbit'),eye=$('#robot-eye'),ctx=eye.getContext('2d',{willReadFrequently:true});
  const detail=document.createElement('canvas');detail.width=320;detail.height=240;
  const semanticContext=detail.getContext('2d',{willReadFrequently:true});
  const draw=new T.WebGLRenderer({canvas,antialias:true,alpha:true});draw.setPixelRatio(Math.min(devicePixelRatio,1.6));draw.setClearColor(0,0);
  const capture=new T.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});capture.setSize(192,144,false);capture.setClearColor(0);
  const gltf=await new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder).loadAsync(new URL('castle.glb',import.meta.url).href);
  const world=new T.Scene();world.add(gltf.scene);
  gltf.scene.traverse(o=>{if(o.isMesh){const m=o.material;o.material=new T.MeshBasicMaterial({map:m.map,color:m.color,vertexColors:!!o.geometry.attributes.color,side:T.DoubleSide,alphaTest:m.alphaTest});}});
  const onboard=new T.PerspectiveCamera(2*Math.atan(Math.tan(78*Math.PI/360)*.75)*180/Math.PI,4/3,.02,100);
  onboard.rotation.order='YXZ';
  const scene=new T.Scene(),cam=new T.PerspectiveCamera(38,1,.02,150);
  scene.add(new T.HemisphereLight(0xffffff,0xacb2a7,1.85));
  const sun=new T.DirectionalLight(0xfffcf4,1.35);sun.position.set(-3,8,4);scene.add(sun);
  const ground=new T.BufferGeometry();ground.setAttribute('position',new T.Float32BufferAttribute(floor.tris.flat(2),3));ground.computeVertexNormals();
  const uv=new Float32Array(floor.tris.length*6);floor.tris.flat().forEach((p,i)=>{uv[i*2]=p[0];uv[i*2+1]=p[2];});ground.setAttribute('uv',new T.BufferAttribute(uv,2));
  const tile=document.createElement('canvas');tile.width=tile.height=128;const ink=tile.getContext('2d');ink.fillStyle='#d9dfd1';ink.fillRect(0,0,128,128);ink.strokeStyle='#c1caba';ink.strokeRect(0,0,128,128);ink.fillStyle='#b9c4b2';for(let i=8;i<128;i+=16)for(let j=8;j<128;j+=16)ink.fillRect(i,j,1.7,1.7);
  const tex=new T.CanvasTexture(tile);tex.wrapS=tex.wrapT=T.RepeatWrapping;tex.colorSpace=T.SRGBColorSpace;
  scene.add(new T.Mesh(ground,new T.MeshBasicMaterial({map:tex,side:T.DoubleSide})));
  // Draw the NavMesh boundary; internal triangulation edges are suppressed.
  const edges=new Map();for(const tri of floor.tris)for(let i=0;i<3;i++){const a=tri[i],b=tri[(i+1)%3],key=[a.join(','),b.join(',')].sort().join('|');if(edges.has(key))edges.delete(key);else edges.set(key,[a,b]);}
  const strips=[],rails=[];for(const [a,b] of edges.values()){const at=[a[0],a[1]+.18,a[2]],bt=[b[0],b[1]+.18,b[2]];strips.push(...a,...b,...at,...at,...b,...bt);rails.push(...at,...bt);}
  const geo=new T.BufferGeometry();geo.setAttribute('position',new T.Float32BufferAttribute(strips,3));geo.computeVertexNormals();scene.add(new T.Mesh(geo,new T.MeshStandardMaterial({color:0xadb9a2,side:T.DoubleSide})));
  const line=new T.BufferGeometry();line.setAttribute('position',new T.Float32BufferAttribute(rails,3));scene.add(new T.LineSegments(line,new T.LineBasicMaterial({color:0x82917e})));
  const grid=new T.GridHelper(80,160,0xc6d0be,0xd5dacf);grid.position.y=-.07;scene.add(grid);
  const {body,legs}=await model();scene.add(body);
  const target=new T.Group(),red=new T.MeshStandardMaterial({color:0xc45239});target.position.fromArray(floor.target);scene.add(target);
  const can=new T.Mesh(new T.CapsuleGeometry(.087,.28,6,16),red);target.add(can);const cap=new T.Mesh(new T.BoxGeometry(.14,.035,.05),new T.MeshStandardMaterial({color:0x333e35}));cap.position.y=.26;target.add(cap);
  const ring=new T.Mesh(new T.RingGeometry(.27,.31,36),new T.MeshBasicMaterial({color:0xce7854,side:T.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=-.27;target.add(ring);
  const breadcrumb=new T.Line(new T.BufferGeometry(),new T.LineBasicMaterial({color:0x478267}));scene.add(breadcrumb);
  let angle=.78,tilt=.68,dist=2.8,drag=null,pose,yaw,steps=0,travel=0,paused=false,finished=false,generation=0,worker,controller,trail=[],timer;
  const redraw=()=>{if(!pose)return;const w=canvas.clientWidth,h=canvas.clientHeight;draw.setSize(w,h,false);cam.aspect=w/h;cam.updateProjectionMatrix();const focus=new T.Vector3(pose.x,pose.y+.17,pose.z);cam.position.set(focus.x+dist*Math.cos(tilt)*Math.sin(angle),focus.y+dist*Math.sin(tilt),focus.z+dist*Math.cos(tilt)*Math.cos(angle));cam.lookAt(focus);draw.render(scene,cam);};
  new ResizeObserver(redraw).observe(canvas);
  canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(!drag)return;angle-=(e.clientX-drag[0])*.012;tilt=Math.max(.2,Math.min(1.35,tilt+(e.clientY-drag[1])*.009));drag=[e.clientX,e.clientY];redraw();};
  canvas.onpointerup=canvas.onpointercancel=()=>drag=null;
  canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();angle+=(e.key==='ArrowLeft'?-.18:e.key==='ArrowRight'?.18:0);tilt=Math.max(.2,Math.min(1.35,tilt+(e.key==='ArrowUp'?.12:e.key==='ArrowDown'?-.12:0)));redraw();}};
  function view(){onPose(pose.x,pose.z,yaw);onboard.position.copy(pose);onboard.position.y+=.46;onboard.rotation.set(-.2,yaw,0,'YXZ');capture.render(world,onboard);ctx.drawImage(capture.domElement,0,0);body.position.copy(pose);body.rotation.y=yaw;redraw();}
  function outcome(msg){finished=true;$('#hold').disabled=true;$('#live-state').textContent=msg;}
  async function tick(id){
    if(id!==generation||finished)return;
    if(paused){timer=setTimeout(()=>tick(id),80);return;}
    try{
      view();const pixels=ctx.getImageData(0,0,192,144).data.buffer;
      semanticContext.drawImage(eye,0,0,320,240);
      const semantic=semanticContext.getImageData(0,0,320,240).data.buffer;
      const {action}=await ask(worker,{type:'frame',pixels,semantic},controller.signal,[pixels,semantic]);if(id!==generation)return;
      $('#elapsed').textContent=(steps*dt).toFixed(2)+' s';const [f,r,stop]=action;
      if(stop){
        // Render target IDs against full scene depth, with the same camera and pose.
        const originals=new Map(),yes=new T.MeshBasicMaterial({color:0xffffff,side:T.DoubleSide}),no=new T.MeshBasicMaterial({color:0,side:T.DoubleSide});
        world.traverse(o=>{if(o.isMesh){originals.set(o,o.material);o.material=o.name.startsWith('registered_C')?yes:no;}});
        capture.render(world,onboard);const label=document.createElement('canvas');label.width=192;label.height=144;
        const g=label.getContext('2d');g.drawImage(capture.domElement,0,0);const masks=g.getImageData(0,0,192,144).data;let visible=0;
        for(let j=0;j<masks.length;j+=4)if(masks[j]>120)visible++;
        originals.forEach((m,o)=>o.material=m);yes.dispose();no.dispose();
        const range=viewpointRange(floor.tris,pose.toArray(),floor.views);
        const metric=range.kind==='within'?'관측점까지 바닥 경로 '+range.distance.toFixed(2)+' m':
          range.kind==='outside'?'관측점 0.8 m 밖':'관측점 거리 미확정';
        outcome('STOP · '+(visible>=8?'소화기 C가 보임':'소화기 C가 보이지 않음')+' · '+metric);return;
      }
      const count=4;let blocked=false;for(let i=0;i<count;i++){
        const turn=r*dt/count,mid=yaw+turn/2;yaw+=turn;const dx=-Math.sin(mid)*f*dt/count,dz=-Math.cos(mid)*f*dt/count;
        const x=pose.x+dx,z=pose.z+dz,y=floorHeight(floor.tris,x,z);
        if(y!==null){pose.set(x,y,z);travel+=Math.hypot(dx,dz);}else blocked=true;
      }
      for(const {hip,knee,phase} of legs){const d=f>0?.27*Math.sin(travel*19)*phase:0;hip.rotation.y=.79+d;knee.rotation.y=-1.54+Math.max(0,-d)*1.4;}
      if(f>.001){trail.push(new T.Vector3(pose.x,pose.y+.025,pose.z));breadcrumb.geometry.dispose();breadcrumb.geometry=new T.BufferGeometry().setFromPoints(trail);}
      steps++;$('#live-state').textContent=blocked?'주행 경계':f>.001?'전진':r>0?'좌회전':'우회전';
      if(steps>=240){view();outcome('60초 주행 종료');return;}timer=setTimeout(()=>tick(id),250/Number($('#rate').value));
    }catch(e){if(id===generation)outcome(e.message);}
  }
  async function reset(){
    $('#rerun').disabled=false;const id=++generation;controller?.abort();worker?.terminate();clearTimeout(timer);controller=new AbortController();worker=new Worker(new URL('../h4/worker.mjs',import.meta.url),{type:'module'});
    const start=getStart();pose=new T.Vector3(...start.xyz);yaw=start.yaw;steps=travel=0;paused=finished=false;trail=[pose.clone()];breadcrumb.geometry.dispose();breadcrumb.geometry=new T.BufferGeometry();legs.forEach(l=>{l.hip.rotation.y=.79;l.knee.rotation.y=-1.54;});
    $('#elapsed').textContent='0.00 s';$('#hold').textContent='일시 정지';$('#hold').disabled=false;$('#live-state').textContent='정책 준비 중';view();
    try{await ask(worker,{type:'start'},controller.signal);if(id===generation)tick(id);}catch(e){if(id===generation)outcome(e.message);}
  }
  $('#hold').onclick=()=>{paused=!paused;$('#hold').textContent=paused?'계속 주행':'일시 정지';};
  $('#rerun').onclick=reset;$('.chipcam').hidden=false;
  function preview(){
    generation++; controller?.abort(); worker?.terminate(); clearTimeout(timer); finished=true;
    const start=getStart(); pose=new T.Vector3(...start.xyz); yaw=start.yaw;
    breadcrumb.geometry.dispose(); breadcrumb.geometry=new T.BufferGeometry();
    $('#elapsed').textContent='0.00 s'; $('#hold').disabled=true; $('#rerun').disabled=true;
    $('#live-state').textContent='출발 대기'; view();
  }
  preview();return {reset,preview};
}
