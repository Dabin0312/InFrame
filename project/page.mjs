const $=s=>document.querySelector(s);
const video=$('#film'),slider=$('#seek'),play=$('#play'),floor=$('#floor'),ctx=floor.getContext('2d');
const fetchJSON=async name=>(await fetch(new URL(name,import.meta.url))).json();
const format=t=>'0:'+String(Math.floor(t)).padStart(2,'0');
let route, background, requestedFrame;
function drawRoute(){
  if(!route||!background)return;
  const time=Math.min(17.25,video.currentTime);
  const i=Math.min(route.steps.length-1,Math.floor(time*4)), step=route.steps[i],next=route.steps[Math.min(i+1,69)],f=time*4-i;
  const p=step.p.map((v,k)=>v+(next.p[k]-v)*f);
  ctx.clearRect(0,0,640,640);ctx.drawImage(background,0,0);ctx.lineCap='round';ctx.lineJoin='round';
  function trail(points,color,width,dash=[]){ctx.beginPath();points.forEach(([x,y],j)=>j?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.setLineDash(dash);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();ctx.setLineDash([]);}
  trail(route.steps.map(r=>r.p),'#88987d',3,[5,8]);trail([...route.steps.slice(0,i+1).map(r=>r.p),p],'#365c42',5);
  const [tx,ty]=route.target;ctx.fillStyle='#b75030';ctx.beginPath();ctx.arc(tx,ty,7,0,7);ctx.fill();ctx.font='bold 19px sans-serif';ctx.fillText('C',tx+11,ty+6);
  const mid=-Math.PI/2-step.yaw;ctx.fillStyle='#7a9a6480';ctx.beginPath();ctx.moveTo(...p);ctx.arc(...p,40,mid-.55,mid+.55);ctx.closePath();ctx.fill();
  ctx.beginPath();ctx.arc(...p,8,0,7);ctx.fillStyle='#294f36';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();
  ctx.fillStyle='#60725d';ctx.font='16px monospace';ctx.fillText('2 m',52,593);trail([[52,573],[52+2*route.scale,573]],'#60725d',2);
}
function sync(){slider.value=Math.min(69,video.currentTime*4);$('#clock').textContent=format(video.currentTime);drawRoute();}
function loop(){sync();if(!video.paused&&!video.ended)requestedFrame=requestAnimationFrame(loop);}
video.addEventListener('loadedmetadata',()=>{video.currentTime=13;});if(video.readyState>=1)video.currentTime=13;
video.addEventListener('seeked',sync);video.addEventListener('timeupdate',sync);
video.addEventListener('play',()=>{play.textContent='Ⅱ';play.setAttribute('aria-label','주행 일시 정지');cancelAnimationFrame(requestedFrame);loop();});
video.addEventListener('pause',()=>{play.textContent='▶';play.setAttribute('aria-label','주행 재생');cancelAnimationFrame(requestedFrame);sync();});
let firstPlay=true;play.onclick=()=>{if(!video.paused)return video.pause();if(firstPlay||video.ended||video.currentTime>=17.24)video.currentTime=0;firstPlay=false;video.play().catch(()=>{video.controls=true;});};
slider.oninput=()=>{firstPlay=false;video.pause();video.currentTime=Number(slider.value)/4;};
$('#end').onclick=()=>{firstPlay=false;video.pause();video.currentTime=17.25;};
async function initMap(){
  route=await fetchJSON('route.json');const img=new Image();img.src=new URL('floor.png',import.meta.url).href;await img.decode();
  background=document.createElement('canvas');background.width=background.height=640;const b=background.getContext('2d');b.drawImage(img,0,0);
  const pixels=b.getImageData(0,0,640,640),d=pixels.data;for(let i=0;i<d.length;i+=4){
    const inside=d[i];if(inside){const edge=i<2560||!d[i-2560]||!d[i+2560]||!d[i-4]||!d[i+4];d[i]=edge?133:206;d[i+1]=edge?148:216;d[i+2]=edge?125:195;}d[i+3]=inside;
  }b.putImageData(pixels,0,0);drawRoute();
}
initMap().catch(()=>{floor.replaceWith('지도를 불러올 수 없습니다.');});
async function initFire(){
  const anchors=await fetchJSON('anchors.json');
  const v=new DataView(await (await fetch(new URL('fire.bin',import.meta.url))).arrayBuffer());
  const canvas=$('#cloud'),c=canvas.getContext('2d');
  function project(x,y,z){const a=.44,b=.27;const u=Math.cos(a)*x+Math.sin(a)*(z-1.9);const depth=-Math.sin(a)*x+Math.cos(a)*(z-1.9);return [307+u*216,240+(Math.cos(b)*y-Math.sin(b)*depth)*216,depth];}
  const points=[];for(let k=0;k<v.byteLength;k+=9){
    const pt=project(...[0,2,4].map(j=>v.getInt16(k+j,true)/1000));
    if(pt[0]<-3||pt[0]>642||pt[1]<-3||pt[1]>482)continue;
    pt.push('rgb('+[6,7,8].map(j=>Math.round(v.getUint8(k+j)*.8+20)).join(',')+')');points.push(pt);
  }points.sort((a,b)=>b[2]-a[2]);
  function select(id){
    c.clearRect(0,0,640,480);points.forEach(([x,y,z,col])=>{c.fillStyle=col;c.fillRect(x,y,2.5,2.5);});
    for(const item of anchors){const [x,y]=project(...item.xyz);const on=item.id===id;c.lineWidth=on?3:1.5;c.strokeStyle=on?'#e2f9a9':'#fff9';c.beginPath();c.arc(x,y,on?12:7,0,7);c.stroke();c.fillStyle=on?'#e2f9a9':'#fff';c.font='bold 19px monospace';c.fillText(item.id,x+12,y-12);}
    const a=anchors.find(x=>x.id===id),[x,y,x2,y2]=a.box,box=$('#bbox');Object.assign(box.style,{left:x/640*100+'%',top:y/480*100+'%',width:(x2-x)/640*100+'%',height:(y2-y)/480*100+'%'});box.firstElementChild.textContent=id;
    $('#coordinate').textContent=id+'  ['+a.xyz.map(x=>x.toFixed(2)).join(', ')+'] m';
    document.querySelectorAll('[data-id]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.id===id));
  }
  select('A');document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>select(b.dataset.id));
}
initFire().catch(()=>{$('#coordinate').textContent='점군을 불러올 수 없습니다.';});
