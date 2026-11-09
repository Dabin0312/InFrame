import {ask,waitEvent} from './rpc.mjs';
const $=s=>document.querySelector(s),video=$('#clip'),screen=$('#camera'),map=$('#map'),mc=map.getContext('2d');
const raw=document.createElement('canvas'),rawctx=raw.getContext('2d',{willReadFrequently:true});
const policy=document.createElement('canvas');policy.width=192;policy.height=144;
const pc=policy.getContext('2d',{willReadFrequently:true});
const options={
  corridor:{url:'../spatial/approach.mp4',name:'SparseVideoNav · 소화기 접근',fov:68},
  full:{url:'../spatial/corridor.mp4',name:'SparseVideoNav · 전체 동선',fov:68},
  desk:{url:'../spatial/desk.mp4',name:'AlvaAR · 작업실',fov:45},
  castle:{url:'../project/castle.mp4',name:'Skokloster Castle · FRESH–015',fov:78}
};
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
  for(const target of targets){const p=px(xy(target.p));markers.push({p,target});dots(mc,p,7,'#cd5e36');mc.fillStyle='#813a24';mc.font='bold 15px sans-serif';mc.fillText((target.reference?'':'E')+target.id,p[0]+9,p[1]-5);}
  if(stop?.pose && stop.seg===seg){const [x,y]=px(xy(stop.pose.slice(12)));mc.strokeStyle='#b76135';mc.lineWidth=3;mc.strokeRect(x-8,y-8,16,16);}
  if(row.pose)dots(mc,px(xy(row.pose.slice(12))),5,'#293933');
}
function display(row,image=video){
  const c=screen.getContext('2d');c.drawImage(image,0,0,screen.width,screen.height);
  for(const b of row.boxes){const [x,y,w,h]=b.box;c.strokeStyle='#ffab57';c.lineWidth=2;c.strokeRect(x,y,w,h);c.fillStyle='#121a14';c.fillRect(x,Math.max(0,y-19),61,19);c.fillStyle='white';c.font='12px sans-serif';c.fillText('E'+b.track+' · '+Math.round(100*b.score)+'%',x+2,Math.max(13,y-5));}
  $('#at').textContent=$('#clock').textContent=seconds(row.t);
  $('#action').textContent=row.action?(row.action[2]?'STOP':row.action[0]>.001?'전진':row.action[1]>0?'좌회전':row.action[1]<0?'우회전':'대기'):(data.stop&&row.t>data.stop.t?'STOP 이후 촬영 구간':'행동 샘플 사이');
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
function targets(){
  const box=$('#targets');box.replaceChildren();
  for(const obj of data.targets){
    const b=document.createElement('button');b.className='pill';b.textContent='소화기 '+(obj.reference?'':'E')+obj.id+' · '+seconds(obj.t)+' ↗';b.onclick=()=>review(obj.reference?Math.round(obj.t*16):data.frames.findIndex(f=>f.seg===obj.seg&&f.pose&&f.boxes.some(x=>x.track===obj.id)));box.append(b);
  }
  if(!box.children.length)box.textContent=data.frames.some(f=>f.boxes.length)?'소화기 검출 · 지도 위치 미확정':'소화기 미검출';
}
const photos={};let mode='inspection';
function activeStop(){return mode==='policy'?data.stop:data.inspection;}
function stopPanel(){
  const event=activeStop(),img=$('#stopimg');img.hidden=!event;$('#nostop').hidden=!!event;
  $('#stopat').textContent=event?seconds(event.t):'';
  $('#stopjump').hidden=!event||!!current;
  if(event){img.src=photos[mode];$('#stopinfo').textContent=event.referenceVisible?'목표 확인 · 장면 마스크':event.targetDetectedInCrop?'소화기 검출':'소화기 미검출';}
  else{$('#nostop').textContent=current?'분석 중':mode==='policy'?'H4 정책의 STOP 없음':'점검 정지 조건 미충족';$('#stopinfo').textContent='';}
}
function inspectionTarget(boxes,history,mapped,w,h){
  // A visible, triangulated target must persist across three of four 4 Hz observations.
  for(const b of boxes){const [x,y,bw,bh]=b.box,center=(x+bw/2)/w;
    if(bh/h<.115||center<.12||center>.88||y<1||y+bh>h-1||!mapped.some(o=>o.id===b.track))continue;
    if(history.filter(ids=>ids.includes(b.track)).length>=3)return b.track;
  }
  return null;
}
async function start(file,key){
  current?.abort();const control=new AbortController(),signal=control.signal;current=control;reviewVersion++;
  if(sourceURL)URL.revokeObjectURL(sourceURL);sourceURL=file?URL.createObjectURL(file):'';
  const conf=file?{name:file.name,fov:68}:options[key];
  mode=key==='castle'&&!file?'policy':'inspection';$('#stopmode').value=mode;delete photos.policy;delete photos.inspection;data={inspection:null,source:conf.name,goal:'fire extinguisher',units:'monocular relative scale per submap',frames:[],points:[],targets:[],stop:null};
  $('#source-name').textContent=conf.name;$('#session').hidden=false;$('#policy-note').textContent='';$('#cancel').hidden=false;
  $('#tick').disabled=true;$('#tick').value=0;$('#stopimg').hidden=true;$('#nostop').hidden=false;$('#nostop').textContent='정책 분석 중';
  $('#stopjump').hidden=$('#download').hidden=true;['#stopat','#stopinfo','#targets','#summary','#action','#at','#mapinfo'].forEach(s=>$(s).textContent='');
  mc.clearRect(0,0,640,440);$('#status').textContent='영상과 모델을 여는 중…';let mw,pw;
  try{
    await waitEvent(video,'loadeddata',signal,()=>{video.src=sourceURL||conf.url;video.load();});
    if(!Number.isFinite(video.duration)||!video.videoWidth)throw Error('영상의 길이를 읽을 수 없어요. H.264 MP4로 시도해 주세요.');
    const portrait=video.videoHeight>video.videoWidth;
    const hz=portrait?32:16,interval=hz/4;data.mappingHz=hz;
    const scale=portrait?Math.min(1.5,920/video.videoHeight):Math.min(1,760/video.videoWidth);
    const w=Math.round(video.videoWidth*scale/2)*2,h=Math.round(video.videoHeight*scale/2)*2;
    raw.width=screen.width=w;raw.height=screen.height=h;
    pw=new Worker(new URL('../demo/policy-worker.mjs',import.meta.url),{type:'module'});
    mw=new Worker(new URL('mapper.mjs',import.meta.url),{type:'module'});
    const [geom]=await Promise.all([ask(mw,{type:'start',w,h,fov:conf.fov},signal),ask(pw,{type:'start'},signal)]);data.intrinsics=geom.k;
    let atlas;if(!file&&key==='castle'){atlas=new Image();atlas.src='sample-rgb.png';await atlas.decode();}
    const ref=atlas?await fetch('../spatial/castle-reference.json').then(r=>r.json()):null;
    if(ref){data.reference='Habitat registered camera poses and observations';data.units='metres, Habitat X/Y/Z';data.targets=[{id:'C',seg:1,p:ref.target,t:17.25,n:1,reference:true}];}
    const history=[];const count=Math.ceil(video.duration*hz-1e-5),vw=video.videoWidth,vh=video.videoHeight,sw=Math.min(vw,vh*4/3),sh=sw*3/4;
    for(let i=0;i<count;i++){
      const t=i/hz,evalPolicy=i%interval===0&&!data.stop;
      if(i)await waitEvent(video,'seeked',signal,()=>{video.currentTime=t;});
      rawctx.drawImage(video,0,0,w,h);
      const rgba=rawctx.getImageData(0,0,w,h).data.buffer;
      const mapping=ask(mw,{type:'frame',t,pixels:rgba,detect:i%interval===0},signal,[rgba]);
      let prediction;
      if(evalPolicy){
        if(atlas){const j=i/4;pc.drawImage(atlas,j%10*192,Math.floor(j/10)*144,192,144,0,0,192,144);}
        else pc.drawImage(video,(vw-sw)/2,(vh-sh)/2,sw,sh,0,0,192,144);
        const pixels=pc.getImageData(0,0,192,144).data.buffer;prediction=ask(pw,{type:'frame',pixels},signal,[pixels]);
      }
      const [r,a]=await Promise.all([mapping,prediction]);const row={t,seg:r.seg,pose:r.pose,state:r.state,boxes:r.boxes,action:a?.action||null};
      if(ref){const j=Math.floor(i/4),next=Math.min(j+1,ref.path.length-1),m=(i%4)/4;
        const center=ref.path[j].map((x,k)=>x+(ref.path[next][k]-x)*m);center[1]+=.46;
        const delta=ref.yaw[next]-ref.yaw[j],heading=ref.yaw[j]+Math.atan2(Math.sin(delta),Math.cos(delta))*m;
        const c=Math.cos(heading),s=Math.sin(heading),pitch=.2,cp=Math.cos(pitch),sp=Math.sin(pitch);
        row.pose=[c,sp*s,-cp*s,0,0,-cp,-sp,0,-s,sp*c,-cp*c,0,...center,1];row.seg=1;row.poseSource='Habitat camera, interpolated';}
      data.frames.push(row);if(!ref){data.points.push(...r.points);if(r.targets)data.targets=r.targets;}
      if(i%interval===0&&!ref){
        history.push(r.boxes.map(b=>b.track));if(history.length>4)history.shift();
        const id=inspectionTarget(r.boxes,history,data.targets,w,h);
        if(!data.inspection&&id&&row.pose){data.inspection={t,seg:row.seg,pose:row.pose,index:i,track:id,targetDetectedInCrop:true};photos.inspection=raw.toDataURL('image/jpeg',.92);stopPanel();}
      }
      if(row.action?.[2]){
        data.stop={t,seg:row.seg,pose:row.pose,index:i,boxes:r.boxes};
        // Preserve the exact RGB observation consumed by the frozen policy.
        photos.policy=policy.toDataURL('image/png');
        data.stop.targetDetectedInCrop=r.boxes.some(({box:[x,y,bw,bh]})=>Math.abs((x+bw/2)/w-.5)<=sw/(2*vw)&&Math.abs((y+bh/2)/h-.5)<=sh/(2*vh));
        if(ref&&i/4===ref.stopIndex)data.stop.referenceVisible=ref.visible;
        stopPanel();
      }
      if(i%interval===0||i===count-1){display(row,raw);$('#status').textContent='분석 중 · '+seconds(t)+' / '+seconds(video.duration)+' · '+Math.round((i+1)/count*100)+'%';}
    }
    $('#status').textContent='분석 완료';$('#tick').max=count-1;$('#tick').disabled=false;$('#download').hidden=false;
    
    targets();$('#summary').textContent=ref?'시뮬레이터 기준 경로 · 정책 관측 70프레임 · 소화기 C':'위치 추적 '+data.frames.filter(f=>f.pose).length+' / '+count+'프레임 · 소화기 관측 '+data.frames.filter(f=>f.boxes.length).length+'프레임 · 지도에 등록한 관측 트랙 '+data.targets.length+'개';
    current=null;stopPanel();$('#policy-note').textContent=data.stop?'H4 정책 첫 STOP '+seconds(data.stop.t):'H4 정책은 이 영상에서 STOP을 출력하지 않았습니다.';
    await review(activeStop()?.index??Math.max(0,data.frames.findLastIndex(r=>r.pose)));
  }catch(e){if(current===control){$('#status').textContent=signal.aborted?'분석을 취소했어요.':String(e.message);$('#nostop').textContent='분석 종료';}}
  finally{mw?.terminate();pw?.terminate();if(current===control)current=null;if(!current)$('#cancel').hidden=true;}
}
$('#file').onchange=e=>{if(e.target.files[0])start(e.target.files[0]);e.target.value='';};
$('#sample').onclick=()=>start(null,$('#example').value);$('#cancel').onclick=()=>current?.abort();
$('#tick').oninput=e=>review(+e.target.value);$('#stopjump').onclick=()=>review(activeStop()?.index);
$('#stopmode').onchange=e=>{mode=e.target.value;if(!data)return;stopPanel();if(!current){const event=activeStop();if(event)review(event.index);else plot(data.frames[selected]);}};
$('#plane').onchange=()=>{const row=current?data?.frames.at(-1):data?.frames[selected];if(row)plot(row);};
$('#download').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.download='inframe-map.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
const drop=$('#drop');drop.ondragover=e=>{e.preventDefault();drop.classList.add('over');};drop.ondragleave=()=>drop.classList.remove('over');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])start(e.dataTransfer.files[0]);};

map.onclick=e=>{if(current||!data)return;const rect=map.getBoundingClientRect(),scale=Math.min(rect.width/map.width,rect.height/map.height);const x=(e.clientX-rect.left-(rect.width-map.width*scale)/2)/scale,y=(e.clientY-rect.top-(rect.height-map.height*scale)/2)/scale;const hit=markers.find(m=>Math.hypot(m.p[0]-x,m.p[1]-y)<18);if(!hit)return;const o=hit.target;review(o.reference?Math.round(o.t*16):data.frames.findIndex(f=>f.seg===o.seg&&f.pose&&f.boxes.some(b=>b.track===o.id)));};

async function openReport(){
  current?.abort();const control=new AbortController(),signal=control.signal;current=control;reviewVersion++;
  try{
    const [response]=await Promise.all([fetch(new URL('approach-report.json',import.meta.url),{signal}),waitEvent(video,'loadeddata',signal,()=>{video.src=options.corridor.url;video.load();})]);
    if(!response.ok)throw Error('공개 검증 결과를 읽지 못했어요.');
    const result=await response.json();if(current!==control)return;data=result;mode='inspection';$('#stopmode').value=mode;photos.inspection='../spatial/inspection.jpg';delete photos.policy;
    screen.width=data.intrinsics.width;screen.height=data.intrinsics.height;$('#source-name').textContent=options.corridor.name;
    $('#session').hidden=false;$('#cancel').hidden=true;$('#tick').disabled=false;$('#tick').max=data.frames.length-1;
    $('#download').hidden=false;$('#status').textContent='공개 실내 영상 · 저장된 브라우저 검증 결과';$('#policy-note').textContent='H4 정책은 이 영상에서 STOP을 출력하지 않았습니다.';
    $('#summary').textContent='위치 추적 '+data.frames.filter(f=>f.pose).length+' / '+data.frames.length+'프레임 · 희소 특징점 '+data.points.length+'개';
    current=null;targets();stopPanel();await review(data.inspection.index);
  }catch(e){if(current===control){current=null;$('#status').textContent=signal.aborted?'분석 취소':e.message;}}
}
$('#report').onclick=openReport;
if(new URLSearchParams(location.search).get('example')==='approach')openReport();
