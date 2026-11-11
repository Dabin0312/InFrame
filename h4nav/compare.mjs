import {openStudy} from './study.mjs';
const $ = id => document.getElementById(id);
const names = ['의자','쓰레기통','소화기','전자레인지 · 없음','쓰레기통 · 제거','소화기 · 제거','의자 · 제거'];
const colours = ['#984c33','#087d6e'];
function status(r){
  if(!r.firstStop)return '마지막 관측 · STOP 없음';
  if(r.audit.distance==null)return '오정지 · 등록 목표 없음';
  return r.success ? '첫 STOP · 목표 확인' : '첫 STOP · 기준 밖';
}
function photo(r, key) {
  const img = $(key+'Photo');
  img.src = r.photo; img.alt = status(r);
  const details = [status(r), r.steps+'스텝', '이동 '+r.travel.toFixed(2)+' m', '막힌 전진 '+r.bumped+'회'];
  if(r.audit.distance!=null) details.push('물체까지 '+r.audit.distance.toFixed(2)+' m', '목표 '+r.audit.visiblePixels+' px');
  if(r.firstStop && r.audit.legacyView) details.push('등록 관측점 0.8 m '+({within:'이내',outside:'밖',unresolved:'미확정'}[r.audit.legacyView]));
  $(key+'Text').textContent = details.join(' · ');
}
function draw(tris,rows,showBlocked){
  const ctx=$('map').getContext('2d'),w=600,h=450;
  const pts=tris.flat(),xs=pts.map(p=>p[0]),zs=pts.map(p=>p[2]);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minZ=Math.min(...zs),maxZ=Math.max(...zs);
  const scale=Math.min((w-30)/(maxZ-minZ),(h-30)/(maxX-minX));
  const xy=(x,z)=>[w/2+(z-(minZ+maxZ)/2)*scale,h/2+(x-(minX+maxX)/2)*scale];
  ctx.fillStyle='#edf2ed';ctx.fillRect(0,0,w,h);ctx.fillStyle='#c7dbcd';ctx.beginPath();
  for(const t of tris){t.forEach(([x,,z],j)=>ctx[j?'lineTo':'moveTo'](...xy(x,z)));ctx.closePath();}ctx.fill();
  rows.forEach((r,i)=>{
    ctx.strokeStyle=colours[i];ctx.lineWidth=i?3.5:5;ctx.setLineDash(i?[7,3]:[]);ctx.beginPath();
    [...r.trace,r.endpoint].forEach(({x,z},j)=>ctx[j?'lineTo':'moveTo'](...xy(x,z)));ctx.stroke();ctx.setLineDash([]);
  });
  if(showBlocked)rows.forEach((r,i)=>{
    ctx.strokeStyle=colours[i];ctx.lineWidth=2;
    r.trace.forEach((p,j)=>{
      const next=r.trace[j+1]??r.endpoint;
      if(p.a!==0||p.x!==next.x||p.z!==next.z)return;
      const [x,y]=xy(p.x,p.z);ctx.beginPath();ctx.arc(x,y,i?4:6,0,Math.PI*2);ctx.stroke();
    });
  });
  const r=rows[0],k=r.scoreKey;
  if(k>=0&&r.removed!==k){
    const [a,b]=xy(...r.anchors[k]);ctx.fillStyle='#402860';ctx.beginPath();[[0,-7],[7,0],[0,7],[-7,0]].forEach(([u,v],i)=>ctx[i?'lineTo':'moveTo'](a+u,b+v));ctx.fill();
  }
  const [sx,sy]=xy(r.start.x,r.start.z);ctx.beginPath();ctx.arc(sx,sy,7,0,2*Math.PI);ctx.fillStyle='white';ctx.fill();ctx.lineWidth=2;ctx.strokeStyle='#203f34';ctx.stroke();
  rows.forEach((r,i)=>{const [x,y]=xy(r.endpoint.x,r.endpoint.z);ctx.lineWidth=2.5;ctx.strokeStyle=colours[i];ctx.fillStyle=colours[i];
    if(r.firstStop){const size=i?6:11;ctx.fillRect(x-size/2,y-size/2,size,size);}
    else{const z=i?4:7;ctx.beginPath();ctx.moveTo(x-z,y-z);ctx.lineTo(x+z,y+z);ctx.moveTo(x+z,y-z);ctx.lineTo(x-z,y+z);ctx.stroke();}
  });
}
async function main(){
  const embedded=JSON.parse($('embedded').textContent);
  const study=await openStudy(embedded);
  const {report,floor,pairs}=study;
  const {holdoutPositive:p,holdoutAbsent:n}=report.metrics;
  $('summary').textContent='새 출발점·배치 '+(report.holdoutCount??4)+'곳에서 목표 도달 '+p.before+' → '+p.after+' / '+p.total+'회. 없는 목표에서 잘못된 STOP '+n.before+' → '+n.after+' / '+n.total+'회.';
  for(const [id,label] of Object.entries(report.layouts))$('layout').add(new Option(label,id));
  study.cases.forEach(i=>$('trial').add(new Option(names[i],i)));
  if(report.diagnosis){
    const d=report.diagnosis;
    $('breakdown').textContent=report.metrics.byCase.slice(0,3).map((m,i)=>names[i]+' '+m.before+' → '+m.after+' / '+m.total+'회').join('　·　');
    $('diagnosis').hidden=false;
    $('diagnosisText').textContent=d.caption;
    $('diagnosisImg').src=d.photo;
    $('studyInfo').textContent=report.description;
    $('json').href=study.file;
    if(study.id==='escape'){
      $('map').nextElementSibling.append('　◎ 전진이 막힌 위치');
      const counts=report.metrics.blockedForward;
      if(counts){
        $('studyInfo').textContent+=' 막힌 전진 합계는 '+study.cases.map(k=>
          names[k]+' '+counts[k].before+' → '+counts[k].after+'회').join(', ')+'입니다.';
      }
      $('diagnosis').querySelector('summary').textContent='기존 2번에서 전진을 여섯 번 막은 경계';
      $('diagnosisImg').alt='중앙에 보였던 의자가 우회전 뒤 시야를 벗어나는 순간';
      $('diagnosisImg').style.maxWidth='100%';
    }
    if(study.id==='chair'){
      $('diagnosis').querySelector('summary').textContent='기존 의자 주행 7번과 22번의 카메라 관측';
      $('diagnosisImg').alt='등록 의자가 시야를 벗어난 순간과 출발 즉시 오정지한 벽면';
      $('diagnosisImg').style.maxWidth='100%';
    }
    if(study.id==='panel'){
      $('diagnosis').querySelector('summary').textContent='기존 다섯 배치에서 쓰레기통이 보였던 순간';
      $('diagnosisImg').alt='기존 H4의 벽면 구역 다섯 주행과 쓰레기통이 가장 크게 보인 실제 RGB';
      $('diagnosisImg').style.maxWidth='100%';
      const counts=report.metrics.strata.panel;
      $('breakdown').textContent+='　·　벽면 구역 쓰레기통 '+counts.present.before+' → '+counts.present.after+' / '+counts.present.total+'회';
    }
    if(study.id==='bin'){
      $('diagnosis').querySelector('summary').textContent='배치 7에서 빈 벽을 보고 멈춘 이유';
      $('diagnosisImg').alt='12번째 벽면 사진과 H4의 내부 쓰레기통 특징 강도';
      $('diagnosisImg').style.maxWidth='660px';
    }
    $('routesFile').href=study.id+'-routes.png';
    $('offlineFile').href=study.id+'-viewer.zip';
    $('evidence').hidden=location.protocol==='file:';
  }
  const params=new URLSearchParams(location.search),layout=params.get('scene');
  if(Object.hasOwn(report.layouts,layout))$('layout').value=layout;
  else if(Object.hasOwn(report.layouts,study.layout))$('layout').value=study.layout;
  const requested=params.get('case');$('trial').value=requested!==null&&Array.from($('trial').options).some(o=>o.value===requested)?requested:String(study.selected);
  let revision=0;
  async function show(){
    const ticket=++revision,id=$('layout').value,i=Number($('trial').value);
    const group=await pairs(id);
    if(ticket!==revision)return;
    const {before,after}=group.find(x=>x.case===i);
    const toggle=$('toggleBin');
    const targetCase=study.cases.includes(6)?0:1;
    const absentCase=study.cases.includes(6)?6:4;
    toggle.hidden=!['bin','panel','chair','escape'].includes(study.id)||![targetCase,absentCase].includes(i);
    if(!toggle.hidden){
      const target=names[targetCase];
      toggle.textContent='같은 배치에서 '+target+(i===targetCase?' 제거 보기':' 있음 보기');
      toggle.onclick=()=>{$('trial').value=String(i===targetCase?absentCase:targetCase);$('trial').dispatchEvent(new Event('change'));};
    }
    draw(floor.tris,[before,after],study.id==='escape');photo(before,'old');photo(after,'new');
    $('facts').textContent='출발 X '+before.start.x.toFixed(2)+' m · Z '+before.start.z.toFixed(2)+' m · 방향 '+(before.start.yaw*180/Math.PI).toFixed(1)+'° · 두 정책 첫 RGB 해시 '+before.firstFrameSHA256.slice(0,12)+' 동일';
    $('live').href='../demo/search.html?study='+study.id+'&scene='+id+'&case='+i;
    $('table').replaceChildren(...group.map(p=>{const tr=document.createElement('tr');for(const label of [names[p.case],status(p.before),status(p.after)]){const td=document.createElement('td');td.textContent=label;tr.append(td);}return tr;}));
  }
  $('layout').onchange=$('trial').onchange=()=>show().catch(e=>{$('facts').textContent=e.message;});await show();
}
main().catch(err=>{$('summary').textContent=err.message;});
