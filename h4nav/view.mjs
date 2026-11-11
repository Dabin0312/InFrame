import {resolveGoal} from '../spatial/prompt.mjs';
import {openStudy} from './study.mjs';
import {experiment} from './run.mjs';
const $=id=>document.getElementById(id),map=$('map').getContext('2d'),eye=$('photo').getContext('2d');
const names={'chair':'의자','trash can':'쓰레기통','fire extinguisher':'소화기','microwave':'전자레인지'};
const colors=['#007c73','#b96321','#7156ad'];
let records=[],floor,current,selected=-1,version=0,env,busy=false,study,generation=0;
const rows=()=>records.filter(r=>r.layout===$('layout').value);
function locks(on){busy=on;for(const id of ['object','layout','removed','run'])$(id).disabled=on;for(const b of $('runs').children)b.disabled=on;}
function draw(r,trace=[...r.trace,r.endpoint],others=true){
  const width=600,height=440,all=floor.tris.flat(),minX=Math.min(...all.map(p=>p[0])),maxX=Math.max(...all.map(p=>p[0])),minZ=Math.min(...all.map(p=>p[2])),maxZ=Math.max(...all.map(p=>p[2]));
  const scale=Math.min((width-36)/(maxZ-minZ),(height-36)/(maxX-minX));
  const xy=(x,z)=>[width/2+(z-(minZ+maxZ)/2)*scale,height/2+(x-(minX+maxX)/2)*scale];
  map.fillStyle='#f2f5ef';map.fillRect(0,0,width,height);map.fillStyle='#cee0d5';
  map.beginPath();for(const tri of floor.tris){tri.forEach(([x,,z],i)=>map[i?'lineTo':'moveTo'](...xy(x,z)));map.closePath();}map.fill();
  function path(pts,color,line){if(!pts.length)return;map.strokeStyle=color;map.lineWidth=line;map.beginPath();pts.forEach((p,i)=>map[i?'lineTo':'moveTo'](...xy(p.x,p.z)));map.stroke();}
  if(others&&r.removed<0)for(const other of rows())if(other.removed<0&&other.firstStop)path([...other.trace,other.endpoint],'#9baba0',1.4);
  path(trace,colors[r.scoreKey]??'#465361',3);
  r.anchors.forEach(([x,z],i)=>{if(i===r.removed)return;const [a,b]=xy(x,z);map.beginPath();map.arc(a,b,4,0,Math.PI*2);map.fillStyle=colors[i];map.fill();map.font='bold 12px sans-serif';map.fillText(['의자','통','소화기'][i],a+5,b-5);});
  for(const [p,fill] of [[r.start,'white'],[trace.at(-1),'#172e2c']]){if(!p)continue;map.fillStyle=fill;map.beginPath();map.arc(...xy(p.x,p.z),5,0,Math.PI*2);map.fill();map.strokeStyle='#193d34';map.lineWidth=1.7;map.stroke();}
}
const goalName=r=>names[r.prompt]??r.prompt;
function end(r){
  if(!r.firstStop)return 'STOP 없음';
  if((r.removed>=0&&r.removed===r.scoreKey)||r.prompt==='microwave')return '오정지 · 등록 목표 없음';
  if(r.scoreKey<0)return 'STOP · 대응 개체 미등록';
  return r.success?'STOP · 목표 확인':'STOP · 기준 밖';
}
function summary(r,source){
  const view=r.audit.legacyView;const legacy=view?' · 등록 관측점 '+({within:'0.8 m 이내',outside:'0.8 m 밖',unresolved:'거리 미확정'}[view]??view)+(view==='outside'&&Number.isFinite(r.audit.viewDistance)?' (직선 '+r.audit.viewDistance.toFixed(2)+' m)':''):'';
  $('state').textContent=source+' · '+goalName(r)+' · '+end(r)+' · '+r.steps+'스텝 · 주행 '+r.travel.toFixed(2)+' m'+
    (r.firstStop&&r.audit.distance!=null?' · 물체까지 '+r.audit.distance.toFixed(2)+' m'+legacy:'');
  $('caption').textContent=r.firstStop?'첫 STOP · 전방 RGB':'마지막 전방 RGB · 120스텝 한도';
}
async function photo(r){const id=++version,im=new Image();im.src=r.photo;await im.decode();if(id!==version)return;eye.drawImage(im,0,0,320,240);}
function buttons(){
  const box=$('runs');box.replaceChildren();rows().forEach((r,i)=>{const b=document.createElement('button'),img=new Image(),title=document.createElement('b'),note=document.createElement('small');img.src=r.photo;img.alt=r.firstStop?'첫 정지 사진':'마지막 관측';title.textContent=goalName(r)+(r.removed>=0?' · 제거':'');note.textContent=end(r);b.append(img,title,note);b.setAttribute('aria-pressed',String(i===selected));b.onclick=()=>show(i);box.append(b);});
}
async function show(i){current=rows()[i];if(!current)return;selected=i;$('compareLink').href='../h4nav/compare.html?study='+study.id+'&scene='+current.layout+'&case='+study.cases[i];$('object').value=goalName(current);$('removed').value=String(current.removed);draw(current);buttons();summary(current,'저장된 주행');await photo(current);}
async function selectLayout(layout,index){
  const id=++generation;locks(true);
  try{
    const pairs=await study.pairs(layout);
    if(id!==generation)return;
    records=pairs.map(p=>p.after);await show(index);
  }catch(e){$('state').textContent=e.message;}finally{if(id===generation)locks(false);}
}
$('layout').onchange=()=>selectLayout($('layout').value,0);
$('run').onclick=async()=>{
  if(busy||!current)return;locks(true);version++;$('state').textContent='목표 이름과 H4를 준비하는 중…';
  try{
    const q=await resolveGoal($('object').value),layout=$('layout').value,removed=Number($('removed').value);
    env??=await experiment({policy:study.policy});const path=[];const run={...current,removed,scoreKey:['chair','trash can','fire extinguisher'].indexOf(q.prompt)};
    const result=await env.run({layout,prompt:q.prompt,removed},(frame,p,i)=>{eye.drawImage(frame,0,0,320,240);path.push(p);draw(run,path,false);$('caption').textContent='로봇 전방 RGB';$('state').textContent=q.prompt+' · '+(i+1)+'스텝 · '+['전진','좌회전','우회전','STOP'][p.a];});
    current=result;selected=-1;buttons();summary(result,'방금 실행한 H4');draw(result);await photo(result);
  }catch(e){$('state').textContent=e.message;}finally{locks(false);}
};
window.addEventListener('pagehide',()=>{env?.close();env=null;});
try{
  study=await openStudy();floor=study.floor;
  if(study.cases.includes(6) && !Array.from($('removed').options).some(o=>o.value==='0')){
    $('removed').add(new Option('의자 제거','0'),1);
  }
  const layouts=$('layout'),params=new URLSearchParams(location.search);
  layouts.replaceChildren(...Object.entries(study.report.layouts).map(([id,title])=>new Option(title,id)));
  const requested=params.get('scene');
  if(Object.hasOwn(study.report.layouts,requested))layouts.value=requested;
  else layouts.value=study.layout;
  const requestedCase=params.get('case');
  const selected=requestedCase!==null&&study.cases.includes(Number(requestedCase))?Number(requestedCase):study.selected;
  const index=study.cases.indexOf(selected);
  $('reportLink').href='../h4nav/'+study.file;
  await selectLayout(layouts.value,index);
}catch(e){$('state').textContent=e.message;}
