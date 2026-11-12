import {cappedAction,period} from '../h4nav/closed-loop-world.mjs';
import {footprint} from './footprint.mjs';
import {go2Rig} from './go2-rig.mjs';
import {registeredGoals,crossesObject} from './goals.mjs';
import {addIndoorGoals} from './indoor-scene.mjs';
import {buildPlanner,followRoute} from './route-planner.mjs';
import {floorHeight,viewpointRange,directFloorLength} from './navmesh.mjs';
import * as T from './three.mjs';
import {ask} from './rpc.mjs';
const $=s=>document.querySelector(s);
const dt=period;
export async function init(floor, getStart, onPose){
  const canvas=$('#orbit'),eye=$('#robot-eye'),ctx=eye.getContext('2d',{willReadFrequently:true});
  const detail=document.createElement('canvas');detail.width=320;detail.height=240;
  const semanticContext=detail.getContext('2d',{willReadFrequently:true});
  const draw=new T.WebGLRenderer({canvas,antialias:true,alpha:true});draw.setPixelRatio(Math.min(devicePixelRatio,1.6));draw.setClearColor(0,0);
  const capture=new T.WebGLRenderer({antialias:false,preserveDrawingBuffer:true});capture.setSize(192,144,false);capture.setClearColor(0);
  const gltf=await new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder).loadAsync(new URL('castle.glb',import.meta.url).href);
  const world=new T.Scene();world.add(gltf.scene);
  gltf.scene.traverse(o=>{if(o.isMesh){const m=o.material;o.material=new T.MeshBasicMaterial({map:m.map,color:m.color,vertexColors:!!o.geometry.attributes.color,side:T.DoubleSide,alphaTest:m.alphaTest,opacity:m.opacity,transparent:m.transparent,depthWrite:m.depthWrite});}});
  const onboard=new T.PerspectiveCamera(2*Math.atan(Math.tan(78*Math.PI/360)*.75)*180/Math.PI,4/3,.02,100);
  onboard.rotation.order='YXZ';
  const scene=new T.Scene(),cam=new T.PerspectiveCamera(38,1,.02,150);
  scene.add(new T.HemisphereLight(0xffffff,0xacb2a7,1.85));
  const sun=new T.DirectionalLight(0xfffcf4,1.35);sun.position.set(-3,8,4);scene.add(sun);
  const ground=new T.BufferGeometry();ground.setAttribute('position',new T.Float32BufferAttribute(floor.tris.flat(2),3));ground.computeVertexNormals();
  const uv=new Float32Array(floor.tris.length*6);floor.tris.flat().forEach((p,i)=>{uv[i*2]=p[0];uv[i*2+1]=p[2];});ground.setAttribute('uv',new T.BufferAttribute(uv,2));
  const tile=document.createElement('canvas');tile.width=tile.height=128;const ink=tile.getContext('2d');ink.fillStyle='#c6dfd6';ink.fillRect(0,0,128,128);ink.strokeStyle='#aecbbf';ink.strokeRect(0,0,128,128);ink.fillStyle='#a8c6b9';for(let i=8;i<128;i+=16)for(let j=8;j<128;j+=16)ink.fillRect(i,j,1.7,1.7);
  const tex=new T.CanvasTexture(tile);tex.wrapS=tex.wrapT=T.RepeatWrapping;tex.colorSpace=T.SRGBColorSpace;
  scene.add(new T.Mesh(ground,new T.MeshBasicMaterial({map:tex,side:T.DoubleSide})));
  // The NavMesh marks admissible robot-centre positions. Draw its boundary flat.
  const support=footprint(floor);
  const lines=[];
  for(const [a,b] of support.boundary)lines.push(a[0],a[1]+.004,a[2],b[0],b[1]+.004,b[2]);
  const outline=new T.BufferGeometry();outline.setAttribute('position',new T.Float32BufferAttribute(lines,3));
  scene.add(new T.LineSegments(outline,new T.LineBasicMaterial({color:0x81a69c})));
  const outside=new T.Mesh(new T.PlaneGeometry(180,180),new T.MeshBasicMaterial({color:0xe9edef}));
  outside.rotation.x=-Math.PI/2;outside.position.y=-.12;scene.add(outside);
  const {body,gait}=await go2Rig();scene.add(body);
  const target=new T.Group(),red=new T.MeshStandardMaterial({color:0xc45239});target.position.fromArray(floor.target);scene.add(target);
  const can=new T.Mesh(new T.CapsuleGeometry(.087,.28,6,16),red);target.add(can);const cap=new T.Mesh(new T.BoxGeometry(.14,.035,.05),new T.MeshStandardMaterial({color:0x333e35}));cap.position.y=.26;target.add(cap);
  const ring=new T.Mesh(new T.RingGeometry(.27,.31,36),new T.MeshBasicMaterial({color:0xce7854,side:T.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=-.27;target.add(ring);
  const registry=registeredGoals(floor);
  await addIndoorGoals(world,scene,registry);
  let plan,route,goal,goalKey,guided,useDetector,startPose,log=[],recordURL,remainingViews,dwell,blockedSteps;
  function clearRecord(){
    $('#live-record').hidden=true;if(recordURL)URL.revokeObjectURL(recordURL);recordURL=null;
  }
  function record(result){
    const json={goal:goalKey,controller:guided?'semantic map + RGB':'transfer-h4',stopModel:useDetector?'YOLOE + three observations':'H4',start:startPose,
      stopPose:pose.toArray(),duration:steps*dt,travel,blockedSteps,log,...result};
    recordURL=URL.createObjectURL(new Blob([JSON.stringify(json)],{type:'application/json'}));
    $('#live-record').href=recordURL;$('#live-record').hidden=false;
  }
  const breadcrumb=new T.Line(new T.BufferGeometry(),new T.LineBasicMaterial({color:0x478267}));scene.add(breadcrumb);
  let angle=.78,tilt=.68,dist=2.8,drag=null,pose,yaw,steps=0,travel=0,paused=false,finished=false,generation=0,worker,controller,trail=[],timer;
  const redraw=()=>{if(!pose)return;const w=canvas.clientWidth,h=canvas.clientHeight;draw.setSize(w,h,false);cam.aspect=w/h;cam.updateProjectionMatrix();const focus=new T.Vector3(pose.x,pose.y+.17,pose.z);cam.position.set(focus.x+dist*Math.cos(tilt)*Math.sin(angle),focus.y+dist*Math.sin(tilt),focus.z+dist*Math.cos(tilt)*Math.cos(angle));cam.lookAt(focus);draw.render(scene,cam);};
  new ResizeObserver(redraw).observe(canvas);
  canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(!drag)return;angle-=(e.clientX-drag[0])*.012;tilt=Math.max(.2,Math.min(1.35,tilt+(e.clientY-drag[1])*.009));drag=[e.clientX,e.clientY];redraw();};
  canvas.onpointerup=canvas.onpointercancel=()=>drag=null;
  canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();angle+=(e.key==='ArrowLeft'?-.18:e.key==='ArrowRight'?.18:0);tilt=Math.max(.2,Math.min(1.35,tilt+(e.key==='ArrowUp'?.12:e.key==='ArrowDown'?-.12:0)));redraw();}};
  function view(){onPose(pose.x,pose.z,yaw);onboard.position.copy(pose);onboard.position.y+=.46;onboard.rotation.set(-.2,yaw,0,'YXZ');capture.render(world,onboard);ctx.drawImage(capture.domElement,0,0,eye.width,eye.height);body.position.copy(pose);body.rotation.y=yaw;redraw();}
  function outcome(msg){finished=true;$('#hold').disabled=true;$('#live-state').textContent=msg;}
  async function tick(id){
    if(id!==generation||finished)return;
    if(paused){timer=setTimeout(()=>tick(id),80);return;}
    try{
      view();const pixels=guided?ctx.getImageData(0,0,192,144).data.buffer:null;
      semanticContext.drawImage(eye,0,0,320,240);
      const semantic=semanticContext.getImageData(0,0,320,240).data.buffer;
      let action,match=null,seen=[];
      if(!guided){
        const rgb=ctx.getImageData(0,0,160,120).data.buffer;
        const d=await ask(worker,{type:'frame',pixels:rgb},controller.signal,[rgb]);
        if(id!==generation)return;
        action=cappedAction(d.action);
      }else if(useDetector){
        const d=await ask(worker,{type:'frame',pixels:semantic,t:steps*dt},controller.signal,[semantic]);
        if(id!==generation)return;
        match=d.match;seen=d.boxes;action=followRoute(route,pose.toArray(),yaw,goal,!!match);
      }else{
        const d=await ask(worker,{type:'frame',pixels,semantic},controller.signal,[pixels,semantic]);
        if(id!==generation)return;
        action=guided?followRoute(route,pose.toArray(),yaw,goal,!!d.action[2]):d.action;
      }
      log.push({t:steps*dt,xyz:pose.toArray(),yaw,action,boxes:seen});
      $('#elapsed').textContent=(steps*dt).toFixed(2)+' s';const [f,r,stop]=action;
      if(stop){
        // Render target IDs against full scene depth, with the same camera and pose.
        const originals=new Map(),yes=new T.MeshBasicMaterial({color:0xffffff,side:T.DoubleSide}),no=new T.MeshBasicMaterial({color:0,side:T.DoubleSide});
        world.traverse(o=>{if(o.isMesh){originals.set(o,o.material);o.material=(goalKey==='extinguisher'?o.name.startsWith('registered_C'):o.userData.goal===goalKey)?yes:no;}});
        capture.render(world,onboard);const label=document.createElement('canvas');label.width=eye.width;label.height=eye.height;
        const g=label.getContext('2d');g.drawImage(capture.domElement,0,0);const masks=g.getImageData(0,0,label.width,label.height).data;let visible=0,overlap=0,xmin=label.width,xmax=-1;
        for(let j=0;j<masks.length;j+=4)if(masks[j]>120){
          const column=(j/4)%label.width;xmin=Math.min(xmin,column);xmax=Math.max(xmax,column);
          visible++;if(match){const x=((j/4)%192+.5)*320/192,y=(Math.floor(j/4/192)+.5)*240/144;
          const [l,t,w,h]=match.box;if(x>=l&&x<l+w&&y>=t&&y<t+h)overlap++;}
        }
        originals.forEach((m,o)=>o.material=m);yes.dispose();no.dispose();
        if(!guided){
          const distance=Math.hypot(pose.x-goal.xyz[0],pose.z-goal.xyz[2]);
          const centered=visible>0&&Math.abs((xmin+xmax)/(2*label.width)-.5)<=.25;
          const success=distance<=1.35&&centered&&visible>=80;
          record({stop:true,visible,centered,distance,success,photo:eye.toDataURL('image/png')});
          outcome('STOP · '+goal.label+' '+goal.id+(success?' 확인':' · 기준 밖')+' · '+distance.toFixed(2)+' m');return;
        }
        const range=viewpointRange(floor.tris,pose.toArray(),goal.views);
        const metric=range.kind==='within'?'관측점까지 바닥 경로 '+range.distance.toFixed(2)+' m':
          range.kind==='outside'?'관측점 0.8 m 밖':'관측점 거리 미확정';
        const same=visible>=8&&(!useDetector||overlap/visible>=.5);
        record({stop:true,visible,overlap,box:match?.box,score:match?.score,range,success:same&&range.kind==='within'&&blockedSteps<3,photo:eye.toDataURL('image/png')});
        outcome('STOP · '+goal.label+' '+goal.id+(same?' 확인':' 미확인')+' · '+metric);return;
      }
      if(guided&&route.length===1&&Math.hypot(pose.x-route[0][0],pose.z-route[0][2])<.19&&Math.abs(r)<.15){
        if(++dwell>=8){
          remainingViews=remainingViews.filter(v=>v!==route.at(-1));
          route=plan(pose.toArray(),remainingViews);dwell=0;
          if(!route){record({stop:false,success:false});outcome('관측점 탐색 종료 · 목표 미확인');return;}
        }
      }else dwell=0;
      const count=4;let blocked=false;for(let i=0;i<count;i++){
        const turn=r*dt/count,mid=yaw+turn/2;yaw+=turn;const dx=-Math.sin(mid)*f*dt/count,dz=-Math.cos(mid)*f*dt/count;
        const x=pose.x+dx,z=pose.z+dz,y=floorHeight(floor.tris,x,z);
        if(y!==null&&support.clear(pose.toArray(),[x,y,z])&&!crossesObject(pose.x,pose.z,x,z)&&Number.isFinite(directFloorLength(floor.tris,pose.toArray(),[x,y,z]))){pose.set(x,y,z);travel+=Math.hypot(dx,dz);}else blocked=true;
      }
      if(blocked){blockedSteps++;if(guided&&blockedSteps>=3){record({stop:false,success:false});outcome('주행 경계에 3회 도달');return;}}
      gait(travel,f>0&&!blocked);
      if(f>.001){trail.push(new T.Vector3(pose.x,pose.y+.025,pose.z));breadcrumb.geometry.dispose();breadcrumb.geometry=new T.BufferGeometry().setFromPoints(trail);}
      steps++;$('#live-state').textContent=blocked?'주행 경계':f>.001?'전진':r>.01?'좌회전':r<-.01?'우회전':'목표 확인 중';
      if(steps>=240){view();record({stop:false,success:false});outcome('60초 주행 종료');return;}timer=setTimeout(()=>tick(id),250/Number($('#rate').value));
    }catch(e){if(id===generation)outcome(e.message);}
  }
  async function reset(){
    $('#rerun').disabled=false;const id=++generation;controller?.abort();worker?.terminate();clearTimeout(timer);controller=new AbortController();goalKey=$('#live-goal').value;goal=registry[goalKey];guided=$('#live-mode').value==='map';useDetector=guided&&goalKey!=='extinguisher';
    eye.width=guided?192:160;eye.height=guided?144:120;capture.setSize(eye.width,eye.height,false);
    worker=new Worker(new URL(!guided?'../h4nav/worker.mjs?policy=transfer':useDetector?'./goal-worker.mjs':'../h4/worker.mjs',import.meta.url),{type:'module'});
    clearRecord();log=[];blockedSteps=0;
    const start=getStart();startPose={xyz:[...start.xyz],yaw:start.yaw};pose=new T.Vector3(...start.xyz);yaw=start.yaw;steps=travel=0;paused=finished=false;trail=[pose.clone()];breadcrumb.geometry.dispose();breadcrumb.geometry=new T.BufferGeometry();gait(0,false);
    $('#elapsed').textContent='0.00 s';$('#hold').textContent='일시 정지';$('#hold').disabled=false;$('#live-state').textContent='정책 준비 중';view();
    if(guided){plan??=buildPlanner(floor);remainingViews=[...goal.views];dwell=0;route=plan(start.xyz,remainingViews);if(!route){outcome('이 출발점에서 관측점까지 연결된 경로가 없습니다.');return;}}
    try{await ask(worker,guided?{type:'start',goal:goalKey,w:320,h:240}:{type:'start',prompt:goal.prompt,w:160,h:120},controller.signal);if(id===generation)tick(id);}catch(e){if(id===generation)outcome(e.message);}
  }
  $('#hold').onclick=()=>{paused=!paused;$('#hold').textContent=paused?'계속 주행':'일시 정지';};
  $('#rerun').onclick=reset;$('.chipcam').hidden=false;
  function preview(){
    clearRecord();generation++; controller?.abort(); worker?.terminate(); clearTimeout(timer); finished=true;
    const start=getStart(); pose=new T.Vector3(...start.xyz); yaw=start.yaw; gait(0,false);
    breadcrumb.geometry.dispose(); breadcrumb.geometry=new T.BufferGeometry();
    $('#elapsed').textContent='0.00 s'; $('#hold').disabled=true; $('#rerun').disabled=true;
    $('#live-state').textContent='출발 대기'; view();
  }
  preview();return {reset,preview};
}
