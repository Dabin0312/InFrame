import {trackConfirmation} from '../spatial/confirmation.mjs';
const el=id=>document.getElementById(id);
const video=el('real-film'),map=el('real-map'),overlay=el('observed');
const ctx=map.getContext('2d'),boxes=overlay.getContext('2d');
const play=el('real-play'),seek=el('real-seek'),clock=el('real-clock');
const start=Number(seek.min),end=Number(seek.max);
let data,project,observations,firstSeen,animation=0,first=true;
const actualTime=()=>Math.min(end,start+video.currentTime);

function cameraMap(t){
  if(!data)return;
  const frameIndex=Math.min(data.frames.length-1,Math.floor(t*data.hz+1e-7));
  const row=data.frames[frameIndex];
  ctx.clearRect(0,0,map.width,map.height);
  ctx.fillStyle='#98afb0';
  for(const point of data.points){const [x,y]=project(point);ctx.fillRect(x-1,y-1,2.3,2.3);}
  ctx.lineWidth=3.3;ctx.strokeStyle='#267877';ctx.beginPath();
  let connected=false;
  for(let i=0;i<=frameIndex;i++){
    const position=data.frames[i].p;
    if(!position){connected=false;continue;}
    const p=project(position);if(connected)ctx.lineTo(...p);else ctx.moveTo(...p);connected=true;
  }
  ctx.stroke();
  for(const goal of data.targets){
    if(t<(firstSeen.get(goal.id)??Infinity))continue;
    const [x,y]=project(goal.p);ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.fillStyle='#ae4a29';ctx.fill();
    ctx.fillStyle='#783c28';ctx.font='bold 16px sans-serif';ctx.fillText('E'+goal.id,x+10,y-2);
  }
  if(row.p){
    const [x,y]=project(row.p);ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);
    ctx.fillStyle='#126460';ctx.fill();ctx.lineWidth=2;ctx.strokeStyle='#fff';ctx.stroke();
    if(t>=end-.001){ctx.strokeStyle='#174749';ctx.strokeRect(x-11,y-11,22,22);ctx.fillStyle='#143d42';ctx.font='bold 16px sans-serif';ctx.fillText('STOP',x+14,y+17);}
  }
  boxes.clearRect(0,0,overlay.width,overlay.height);
  // Hold the most recent 4 Hz detector observation between consecutive camera frames.
  for(const [id,x,y,w,h] of observations[frameIndex-frameIndex%(data.hz/4)] || []){
    boxes.strokeStyle='#b7ffe1';boxes.lineWidth=2;boxes.strokeRect(x,y,w,h);
    boxes.fillStyle='#154b45';boxes.fillRect(x,y-17,27,17);boxes.fillStyle='#fff';boxes.font='bold 12px sans-serif';boxes.fillText('E'+id,x+3,y-4);
  }
}
function sync(){const t=actualTime();clock.textContent=t.toFixed(2)+' s';seek.value=t;cameraMap(t);}
function tick(){sync();if(actualTime()>=end){video.pause();return;}if(!video.paused)animation=requestAnimationFrame(tick);}
function go(t){video.pause();if(video.readyState>=1)video.currentTime=t-start;}
let castleLoad;
async function prepareCastle(){
  const film=el('film'),response=await fetch(film.dataset.src);
  if(!response.ok)throw Error('castle');
  const blob=await response.blob();
  await new Promise((resolve,reject)=>{
    film.addEventListener('loadeddata',resolve,{once:true});
    film.addEventListener('error',reject,{once:true});
    film.src=URL.createObjectURL(blob);film.load();
  });
  for(const id of ['play','seek','end'])el(id).disabled=false;
}
function choose(which){
  for(const name of ['real','sim']){const on=name===which;el('show-'+name).setAttribute('aria-pressed',String(on));el(name+'-replay').hidden=!on;}
  el('stop-review').hidden=which!=='real';
  if(which==='sim'){
    video.pause();
    castleLoad??=prepareCastle().catch(()=>{castleLoad=null;el('sim-replay').querySelector('figcaption span').textContent='영상을 불러오지 못했습니다. 실제 영상 탭으로 이동한 뒤 다시 선택해 주세요.';});
  }else el('film').pause();
}
el('show-real').onclick=()=>choose('real');el('show-sim').onclick=()=>choose('sim');
play.onclick=()=>{if(!video.paused){video.pause();return;}if(first||actualTime()>=end-.02)video.currentTime=0;first=false;video.play().catch(()=>video.controls=true);};
el('real-end').onclick=()=>{first=false;go(end);};
seek.oninput=()=>{first=false;go(Number(seek.value));};
video.onplay=()=>{play.textContent='Ⅱ';play.setAttribute('aria-label','실제 영상 일시 정지');cancelAnimationFrame(animation);tick();};
video.onpause=()=>{cancelAnimationFrame(animation);play.textContent='▶';play.setAttribute('aria-label','실제 영상 재생');sync();};
video.onseeked=sync;video.ontimeupdate=sync;
async function init(){
  const [resp,clip]=await Promise.all([fetch(new URL('corridor-map.json',import.meta.url)),fetch(new URL('corridor.mp4',import.meta.url))]);
  if(!clip.ok)throw Error('video');video.src=URL.createObjectURL(await clip.blob());
  if(!resp.ok)throw Error('map');data=await resp.json();
  const confirm=trackConfirmation();observations=[];firstSeen=new Map();
  for(let i=0;i<data.frames.length;i+=data.hz/4){
    const row=data.frames[i],t=i/data.hz;
    const ids=confirm(t,row.seg,row.b.map(b=>b[0]));
    observations[i]=row.b.filter(b=>ids.has(b[0]));
    for(const id of ids)if(!firstSeen.has(id))firstSeen.set(id,t);
  }
  const extent=[0,1].map(k=>{
    const cloud=data.points.map(p=>p[k]).sort((a,b)=>a-b),guide=data.frames.filter(f=>f.p).map(f=>f.p[k]).concat(data.targets.map(t=>t.p[k]),cloud[Math.floor(cloud.length*.03)],cloud[Math.floor(cloud.length*.97)]);
    return [Math.min(...guide),Math.max(...guide)];
  });
  const scale=Math.min(535/(extent[0][1]-extent[0][0]),330/(extent[1][1]-extent[1][0]));
  project=p=>p.map((v,k)=>(k?240:320)+(v-(extent[k][0]+extent[k][1])/2)*scale);
  if(video.readyState<1)await new Promise(resolve=>video.addEventListener('loadedmetadata',resolve,{once:true}));
  if(first&&video.paused){video.currentTime=end-start;cameraMap(end);}else sync();
}
init().catch(()=>{const note=document.createElement('span');note.textContent='지도 데이터를 불러오지 못했습니다.';map.replaceWith(note);});

function revealReview(){
  if(location.hash==='#stop-review'){choose('real');el('stop-review').open=true;}
}
revealReview();window.addEventListener('hashchange',revealReview);
