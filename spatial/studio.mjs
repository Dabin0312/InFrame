import {goals,VisualStop} from './goals.mjs';
import {trackConfirmation} from './confirmation.mjs';
import {ask,waitEvent} from './rpc.mjs';
const $=s=>document.querySelector(s),video=$('#clip'),screen=$('#camera'),map=$('#map'),mc=map.getContext('2d');
const raw=document.createElement('canvas'),rawctx=raw.getContext('2d',{willReadFrequently:true});
const policy=document.createElement('canvas');policy.width=192;policy.height=144;
const pc=policy.getContext('2d',{willReadFrequently:true});
const semantic=document.createElement('canvas');semantic.width=320;semantic.height=240;
const sc=semantic.getContext('2d',{willReadFrequently:true});
const options={
  chair:{url:'../spatial/chair-walk.mp4',name:'SparseVideoNav · 전시장 의자',fov:68},
  bin:{url:'../spatial/bin-walk.mp4',name:'SparseVideoNav · 흰 쓰레기통',fov:68},
  corridor:{url:'../spatial/approach.mp4',name:'SparseVideoNav · 소화기 접근',fov:68},
  full:{url:'../spatial/corridor.mp4',name:'SparseVideoNav · 전체 동선',fov:68},
  desk:{url:'../spatial/desk.mp4',name:'AlvaAR · 작업실',fov:45},
  castle:{url:'../project/castle.mp4',name:'Skokloster Castle · FRESH–015',fov:78}
};
let lastSource;
function activeGoal(){return goals[data?.goalKey??'extinguisher'];}
function syncGoalUI(key){
  const h4=key==='extinguisher',modeSelect=$('#stopmode');
  modeSelect.options[0].textContent=h4?'개선 H4 · 첫 STOP':'목표 확인 · 첫 STOP';
  modeSelect.options[1].disabled=!h4;modeSelect.disabled=!h4;
}
let markers=[];let current,sourceURL='',data=null,selected=0,reviewVersion=0;
const seconds=t=>t.toFixed(2)+' s';
function dots(ctx,point,r,color){ctx.beginPath();ctx.arc(...point,r,0,2*Math.PI);ctx.fillStyle=color;ctx.fill();}
function plot(row){
  markers=[];const plane=$('#plane').value==='xz'?2:1,seg=row.seg;
  const xy=p=>[p[0],p[plane]];
  const points=data.points.filter(v=>v.seg===seg).map(v=>xy(v.p));
  const track=data.frames.filter(v=>v.seg===seg&&v.pose).map(v=>xy(v.pose.slice(12)));
  const targets=data.targets.filter(v=>v.seg===seg),stop=activeStop();
  mc.clearRect(0,0,map.width,map.height);
  mc.strokeStyle='#dfe4d8';mc.lineWidth=1;for(let x=0;x<640;x+=32){mc.beginPath();mc.moveTo(x,0);mc.lineTo(x,440);mc.stroke();}for(let y=0;y<440;y+=32){mc.beginPath();mc.moveTo(0,y);mc.lineTo(640,y);mc.stroke();}
  if(!track.length){mc.fillStyle='#707b6b';mc.font='19px sans-serif';mc.fillText(current?'카메라 이동을 관측하는 중':'이 구간의 위치를 복원하지 못했어요',26,215);return;}
  const sorted=d=>points.map(p=>p[d]).sort((a,b)=>a-b);
  const bounds=[0,1].map(i=>{
    const sortedPoints=sorted(i),core=track.map(p=>p[i]).concat(targets.map(t=>xy(t.p)[i]));
    if(sortedPoints.length)core.push(sortedPoints[Math.floor(sortedPoints.length*.04)],sortedPoints[Math.floor(sortedPoints.length*.94)]);
    return [Math.min(...core),Math.max(...core)];
  });
  const scale=Math.min(544/Math.max(.02,bounds[0][1]-bounds[0][0]),350/Math.max(.02,bounds[1][1]-bounds[1][0]));
  const px=p=>[320+(p[0]-(bounds[0][0]+bounds[0][1])/2)*scale,220+(p[1]-(bounds[1][0]+bounds[1][1])/2)*scale];
  for(const p of points)dots(mc,px(p),2.1,'#859380');
  mc.beginPath();let previous=false;for(const f of data.frames){if(f.seg!==seg||!f.pose){previous=false;continue;}const p=px(xy(f.pose.slice(12)));if(previous)mc.lineTo(...p);else mc.moveTo(...p);previous=true;}mc.lineWidth=3;mc.strokeStyle='#4e845e';mc.stroke();
  for(const target of targets){const p=px(xy(target.p));markers.push({p,target});if(stop?.track===target.id&&stop.seg===target.seg){mc.beginPath();mc.arc(...p,11,0,Math.PI*2);mc.strokeStyle='#963e1f';mc.lineWidth=2;mc.stroke();}dots(mc,p,7,'#cd5e36');mc.fillStyle='#813a24';mc.font='bold 15px sans-serif';mc.fillText((target.reference?'':activeGoal().prefix)+target.id,p[0]+9,p[1]-5);}
  if(stop?.pose && stop.seg===seg){const [x,y]=px(xy(stop.pose.slice(12)));mc.strokeStyle='#b76135';mc.lineWidth=3;mc.strokeRect(x-8,y-8,16,16);}
  if(row.pose)dots(mc,px(xy(row.pose.slice(12))),5,'#293933');
}
function display(row,image=video){
  const c=screen.getContext('2d');c.drawImage(image,0,0,screen.width,screen.height);
  for(const b of row.boxes.filter(b=>b.confirmed)){const [x,y,w,h]=b.box;c.strokeStyle='#ffab57';c.lineWidth=2;c.strokeRect(x,y,w,h);c.fillStyle='#121a14';c.fillRect(x,Math.max(0,y-19),61,19);c.fillStyle='white';c.font='12px sans-serif';c.fillText(activeGoal().prefix+b.track+' · '+Math.round(100*b.score)+'%',x+2,Math.max(13,y-5));}
  $('#at').textContent=$('#clock').textContent=seconds(row.t);
  const act=mode==='before'?row.baseline:row.action,stop=activeStop();
  $('#action').textContent=act?(mode==='before'?'기존 H4 · ':data.goalKey&&data.goalKey!=='extinguisher'?'목표 관측 · ':'개선 H4 · ')+(act[2]?'STOP':act[0]>.001?'전진':act[1]>0?'좌회전':act[1]<0?'우회전':'대기'):(stop&&row.t>stop.t?'STOP 이후 촬영 구간':data.goalKey&&data.goalKey!=='extinguisher'?'목표 관측 중':'행동 샘플 사이');
  $('#mapinfo').textContent=data.reference?'시뮬레이터 기준 지도 · 기록된 카메라 위치':'지도 '+row.seg+' · 특징점 '+data.points.filter(p=>p.seg===row.seg).length+' · '+(row.pose?'위치 추적':'위치 미확정');plot(row);
}
async function review(index){
  if(!data||current)return;const row=data.frames[index];if(!row)return;
  const version=++reviewVersion;selected=index;$('#tick').value=index;
  if(video.seeking||Math.abs(video.currentTime-row.t)>.0001){
    const on=new AbortController();
    try{await waitEvent(video,'seeked',on.signal,()=>{if(Math.abs(video.currentTime-row.t)>.0001)video.currentTime=row.t;});}catch{return;}
  }
  if(version===reviewVersion&&!current)display(row);
}
function markConfirmed(row,confirm){
  const ids=confirm(row.t,row.seg,row.boxes.map(b=>b.track));
  for(const box of row.boxes)box.confirmed=ids.has(box.track);
}
function firstObservation(id,seg){
  const has=(r,confirmed)=>r.seg===seg&&r.pose&&r.boxes.some(b=>b.track===id&&(!confirmed||b.confirmed));
  const confirmed=data.frames.findIndex(r=>has(r,true));
  return confirmed>=0?confirmed:data.frames.findIndex(r=>has(r,false));
}
function targets(){
  const box=$('#targets');box.replaceChildren();
  for(const obj of data.targets){
    const b=document.createElement('button');b.className='pill';b.textContent=activeGoal().label+' '+(obj.reference?'':activeGoal().prefix)+obj.id+' · '+seconds(obj.t)+' ↗';b.onclick=()=>review(obj.reference?Math.round(obj.t*16):firstObservation(obj.id,obj.seg));box.append(b);
  }
  if(!box.children.length)box.textContent=data.frames.some(f=>f.boxes.some(b=>b.confirmed))?activeGoal().label+' 검출 · 지도 위치 미확정':activeGoal().label+' 미검출';
}
let mode='policy';
function activeStop(){return mode==='policy'?data.stop:data.before;}
function stopPanel(){
  const event=activeStop(),img=$('#stopimg');img.hidden=!event;$('#nostop').hidden=!!event;
  $('#stopat').textContent=event?seconds(event.t):'';
  $('#stopjump').hidden=!event||!!current;
  if(event){img.alt=activeGoal().label+' 첫 STOP 사진';img.src=event.annotatedPhoto??event.photo;const target=data.targets.find(g=>g.seg===event.seg&&g.id===event.track);
    const identity=event.track?activeGoal().label+' '+activeGoal().prefix+event.track+' · '+(target?'물체 지도 등록':'물체 위치 미확정')+' / ':'';
    $('#stopinfo').textContent=identity+(event.pose?'정지 위치 표시':'정지 위치 미확정');}
  else{$('#nostop').textContent=current?'분석 중':'정책 STOP 없음';$('#stopinfo').textContent='';}
}
function policyNote(){
  const fmt=e=>e?seconds(e.t):'없음';
  $('#policy-note').textContent=(!data.goalKey||data.goalKey==='extinguisher')?'첫 STOP · 기존 H4 '+fmt(data.before)+' / 개선 H4 '+fmt(data.stop):
    activeGoal().label+' · 같은 개체를 세 번 연속 확인한 첫 STOP '+fmt(data.stop);
}
async function loadClip(file,url,signal){
  let blob=file;
  if(!blob){const response=await fetch(url,{signal});if(!response.ok)throw Error('공개 영상을 읽을 수 없습니다.');blob=await response.blob();}
  if(signal.aborted)throw new DOMException('취소','AbortError');
  if(sourceURL)URL.revokeObjectURL(sourceURL);sourceURL=URL.createObjectURL(blob);
  await waitEvent(video,'loadeddata',signal,()=>{video.src=sourceURL;video.load();});
}
async function start(file,key){
  current?.abort();const control=new AbortController(),signal=control.signal;current=control;reviewVersion++;

  lastSource={file,key};const goalKey=$('#upload-goal').value,h4=goalKey==='extinguisher';syncGoalUI(goalKey);
  const conf=file?{name:file.name,fov:68}:options[key];
  mode='policy';$('#stopmode').value=mode;data={version:3,before:null,source:conf.name,goalKey,goal:goals[goalKey].prompt,units:'monocular relative scale per submap',frames:[],points:[],targets:[],stop:null};
  $('#source-name').textContent=conf.name;$('#session').hidden=false;$('#policy-note').textContent='';$('#cancel').hidden=false;
  $('#tick').disabled=true;$('#tick').value=0;$('#stopimg').hidden=true;$('#nostop').hidden=false;$('#nostop').textContent='정책 분석 중';
  $('#stopjump').hidden=$('#download').hidden=true;['#stopat','#stopinfo','#targets','#summary','#action','#at','#mapinfo'].forEach(s=>$(s).textContent='');
  screen.getContext('2d').clearRect(0,0,screen.width,screen.height);mc.clearRect(0,0,640,440);$('#status').textContent='영상과 모델을 여는 중…';let mw,pw;
  try{
    await loadClip(file,conf.url,signal);
    if(!Number.isFinite(video.duration)||!video.videoWidth)throw Error('영상의 길이를 읽을 수 없어요. H.264 MP4로 시도해 주세요.');
    const portrait=video.videoHeight>video.videoWidth;
    const hz=portrait?32:16,interval=hz/4;data.mappingHz=hz;
    const scale=portrait?Math.min(1.5,920/video.videoHeight):Math.min(1,760/video.videoWidth);
    const w=Math.round(video.videoWidth*scale/2)*2,h=Math.round(video.videoHeight*scale/2)*2;
    raw.width=screen.width=w;raw.height=screen.height=h;
    if(h4)pw=new Worker(new URL('../h4/worker.mjs',import.meta.url),{type:'module'});
    mw=new Worker(new URL('mapper.mjs',import.meta.url),{type:'module'});
    const [geom]=await Promise.all([ask(mw,{type:'start',w,h,fov:conf.fov,goal:goalKey},signal),pw&&ask(pw,{type:'start'},signal)]);data.intrinsics=geom.k;
    const confirm=trackConfirmation(),visualStop=new VisualStop();
    let atlas;if(h4&&!file&&key==='castle'){atlas=new Image();atlas.src='sample-rgb.png';await atlas.decode();}
    const ref=atlas?await fetch('../spatial/castle-reference.json').then(r=>r.json()):null;
    if(ref){data.reference='Habitat registered camera poses and observations';data.units='metres, Habitat X/Y/Z';data.targets=[{id:'C',seg:1,p:ref.target,t:17.25,n:1,reference:true}];}
    const count=Math.ceil(video.duration*hz-1e-5),vw=video.videoWidth,vh=video.videoHeight,sw=Math.min(vw,vh*4/3),sh=sw*3/4;
    for(let i=0;i<count;i++){
      const t=i/hz,evalPolicy=h4&&i%interval===0&&(!data.before||!data.stop);
      if(i)await waitEvent(video,'seeked',signal,()=>{video.currentTime=t;});
      rawctx.drawImage(video,0,0,w,h);
      const rgba=rawctx.getImageData(0,0,w,h).data.buffer;
      const mapping=ask(mw,{type:'frame',t,pixels:rgba,detect:i%interval===0},signal,[rgba]);
      let prediction;
      if(evalPolicy){
        if(atlas){const j=i/4;pc.drawImage(atlas,j%10*192,Math.floor(j/10)*144,192,144,0,0,192,144);}
        else pc.drawImage(video,(vw-sw)/2,(vh-sh)/2,sw,sh,0,0,192,144);
        if(atlas)sc.drawImage(policy,0,0,320,240);else sc.drawImage(video,(vw-sw)/2,(vh-sh)/2,sw,sh,0,0,320,240);
        const pixels=pc.getImageData(0,0,192,144).data.buffer,semantic=sc.getImageData(0,0,320,240).data.buffer;
        prediction=ask(pw,{type:'frame',pixels,semantic},signal,[pixels,semantic]);
      }
      const [r,a]=await Promise.all([mapping,prediction]);const row={t,seg:r.seg,pose:r.pose,state:r.state,boxes:r.boxes,action:!data.stop?a?.action||null:null,baseline:!data.before?a?.baseline||null:null,scores:a?.raw||null};
      if(ref){const j=Math.floor(i/4),next=Math.min(j+1,ref.path.length-1),m=(i%4)/4;
        const center=ref.path[j].map((x,k)=>x+(ref.path[next][k]-x)*m);center[1]+=.46;
        const delta=ref.yaw[next]-ref.yaw[j],heading=ref.yaw[j]+Math.atan2(Math.sin(delta),Math.cos(delta))*m;
        const c=Math.cos(heading),s=Math.sin(heading),pitch=.2,cp=Math.cos(pitch),sp=Math.sin(pitch);
        row.pose=[c,sp*s,-cp*s,0,0,-cp,-sp,0,-s,sp*c,-cp*c,0,...center,1];row.seg=1;row.poseSource='Habitat camera, interpolated';}
      let match=null;
      if(i%interval===0){
        markConfirmed(row,confirm);
        if(!h4&&!data.stop){
          match=visualStop.step(row.boxes,w,h,t,row.seg);
          if(match)row.action=[0,0,1];
        }
      }
      if(signal.aborted||current!==control)throw new DOMException('취소','AbortError');
      data.frames.push(row);if(!ref){data.points.push(...r.points);if(r.targets)data.targets=r.targets;}
      for(const [key,action,canvas] of [['before',row.baseline,policy],['stop',row.action,h4?semantic:raw]]){
        if(data[key]||!action?.[2])continue;
        let annotatedPhoto;
        if(match){
          const photo=document.createElement('canvas');photo.width=w;photo.height=h;
          const ink=photo.getContext('2d');ink.drawImage(raw,0,0);
          const [x,y,bw,bh]=match.box;ink.lineWidth=Math.max(2,w/270);ink.strokeStyle='#9bffd4';ink.strokeRect(x,y,bw,bh);
          ink.fillStyle='#16493e';ink.fillRect(x,Math.max(0,y-20),36,20);ink.fillStyle='white';ink.font='bold 14px sans-serif';
          ink.fillText(activeGoal().prefix+match.track,x+4,Math.max(15,y-5));annotatedPhoto=photo.toDataURL('image/png');
        }
        data[key]={t,annotatedPhoto,seg:row.seg,pose:row.pose,index:i,track:match?.track,box:match?.box,photo:canvas.toDataURL('image/png'),scores:row.scores};
        stopPanel();
      }
      if(i%interval===0||i===count-1){display(row,raw);$('#status').textContent='분석 중 · '+seconds(t)+' / '+seconds(video.duration)+' · '+Math.round((i+1)/count*100)+'%';}
    }
    $('#status').textContent='분석 완료';$('#tick').max=count-1;$('#tick').disabled=false;$('#download').hidden=false;
    
    targets();$('#summary').textContent=ref?'시뮬레이터 기준 경로 · 정책 관측 70프레임 · 소화기 C':'위치 추적 '+data.frames.filter(f=>f.pose).length+' / '+count+'프레임 · '+activeGoal().label+' 관측 '+data.frames.filter(f=>f.boxes.some(b=>b.confirmed)).length+'프레임 · 지도에 등록한 관측 트랙 '+data.targets.length+'개';
    current=null;stopPanel();policyNote();
    await review(activeStop()?.index??Math.max(0,data.frames.findLastIndex(r=>r.pose)));
  }catch(e){if(current===control){$('#status').textContent=signal.aborted?'분석을 취소했어요.':String(e.message);$('#nostop').textContent='분석 종료';}}
  finally{mw?.terminate();pw?.terminate();if(current===control)current=null;if(!current)$('#cancel').hidden=true;}
}
$('#upload-goal').onchange=()=>{
  if(lastSource)start(lastSource.file,lastSource.key);
  else {const key=$('#upload-goal').value;$('#example').value=key==='extinguisher'?'corridor':key;syncGoalUI(key);$('#status').textContent=goals[$('#upload-goal').value].label+' 탐색 · 영상을 선택하세요.';}
};
$('#file').onchange=e=>{if(e.target.files[0])start(e.target.files[0]);e.target.value='';};
$('#sample').onclick=()=>start(null,$('#example').value);$('#cancel').onclick=()=>current?.abort();
$('#tick').oninput=e=>review(+e.target.value);$('#stopjump').onclick=()=>review(activeStop()?.index);
$('#stopmode').onchange=e=>{mode=e.target.value;if(!data)return;stopPanel();if(!current){const event=activeStop();if(event)review(event.index);else display(data.frames[selected]);}};
$('#plane').onchange=()=>{const row=current?data?.frames.at(-1):data?.frames[selected];if(row)plot(row);};
$('#download').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.download='inframe-map.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
const drop=$('#drop');drop.ondragover=e=>{e.preventDefault();drop.classList.add('over');};drop.ondragleave=()=>drop.classList.remove('over');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])start(e.dataTransfer.files[0]);};

map.onclick=e=>{if(current||!data)return;const rect=map.getBoundingClientRect(),scale=Math.min(rect.width/map.width,rect.height/map.height);const x=(e.clientX-rect.left-(rect.width-map.width*scale)/2)/scale,y=(e.clientY-rect.top-(rect.height-map.height*scale)/2)/scale;const hit=markers.find(m=>Math.hypot(m.p[0]-x,m.p[1]-y)<18);if(!hit)return;const o=hit.target;review(o.reference?Math.round(o.t*16):firstObservation(o.id,o.seg));};

async function openReport(){
  $('#upload-goal').value='extinguisher';syncGoalUI('extinguisher');lastSource={file:null,key:'corridor'};
  current?.abort();const control=new AbortController(),signal=control.signal;current=control;reviewVersion++;
  try{
    const [response]=await Promise.all([fetch(new URL('approach-report.json',import.meta.url),{signal}),loadClip(null,options.corridor.url,signal)]);
    if(!response.ok)throw Error('공개 검증 결과를 읽지 못했어요.');
    const result=await response.json();if(current!==control)return;data=result;const confirm=trackConfirmation();
    data.frames.forEach((row,i)=>{if(i%(data.mappingHz/4)===0)markConfirmed(row,confirm);});
    mode='policy';$('#stopmode').value=mode;
    screen.width=data.intrinsics.width;screen.height=data.intrinsics.height;$('#source-name').textContent=options.corridor.name;
    $('#session').hidden=false;$('#cancel').hidden=true;$('#tick').disabled=false;$('#tick').max=data.frames.length-1;
    $('#download').hidden=false;$('#status').textContent='공개 실내 영상 · 저장된 브라우저 검증 결과';policyNote();
    $('#summary').textContent='위치 추적 '+data.frames.filter(f=>f.pose).length+' / '+data.frames.length+'프레임 · 희소 특징점 '+data.points.length+'개';
    current=null;targets();stopPanel();await review(data.stop?.index??data.frames.length-1);
  }catch(e){if(current===control){current=null;$('#status').textContent=signal.aborted?'분석 취소':e.message;}}
}
$('#report').onclick=openReport;
const query=new URLSearchParams(location.search),example=query.get('example'),initialGoal=query.get('goal');
if(example==='approach')openReport();
else if(Object.hasOwn(goals,initialGoal)){
  $('#upload-goal').value=initialGoal;syncGoalUI(initialGoal);
  $('#example').value=initialGoal==='extinguisher'?'corridor':initialGoal;
  if(example===initialGoal&&options[example])start(null,example);
}
