const $ = id => document.getElementById(id);
const names = ['의자','쓰레기통','소화기','전자레인지 · 없음','쓰레기통 · 제거'];
const colours = ['#984c33','#087d6e'];
function status(r){
  return r.firstStop ? (r.success ? '첫 STOP · 목표 확인' : '첫 STOP · 기준 밖') : '마지막 관측 · STOP 없음';
}
function photo(r, key) {
  const img = $(key+'Photo');
  img.src = r.photo; img.alt = status(r);
  const details = [status(r), r.steps+'스텝', '이동 '+r.travel.toFixed(2)+' m', '막힌 전진 '+r.bumped+'회'];
  if(r.firstStop && r.audit.distance!=null) details.push('물체까지 '+r.audit.distance.toFixed(2)+' m', '목표 '+r.audit.visiblePixels+' px');
  if(r.firstStop && r.audit.legacyView) details.push('등록 관측점 0.8 m '+({within:'이내',outside:'밖',unresolved:'미확정'}[r.audit.legacyView]));
  $(key+'Text').textContent = details.join(' · ');
}
function draw(tris,rows){
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
  const read=async u=>{const res=await fetch(u);if(!res.ok)throw Error('검증 파일을 불러올 수 없습니다.');return res.json();};
  const [report, floor]=embedded??await Promise.all([read('comparison.json'),read('../spatial/floor.json')]);
  const {holdoutPositive:p,holdoutAbsent:n}=report.metrics;
  $('summary').textContent='새 출발점·배치 4곳에서 목표 도달 '+p.before+' → '+p.after+' / '+p.total+'회. 없는 목표에서 잘못된 STOP '+n.before+' → '+n.after+' / '+n.total+'회.';
  for(const [id,label] of Object.entries(report.layouts))$('layout').add(new Option(label,id));
  names.forEach((name,i)=>$('trial').add(new Option(name,i)));
  const params=new URLSearchParams(location.search),layout=params.get('scene');
  if(Object.hasOwn(report.layouts,layout))$('layout').value=layout;
  const requested=params.get('case');$('trial').value=/^[0-4]$/.test(requested)?requested:'1';
  function show(){
    const id=$('layout').value,i=Number($('trial').value),group=report.pairs.filter(x=>x.layout===id);
    const {before,after}=group.find(x=>x.case===i);
    draw(floor.tris,[before,after]);photo(before,'old');photo(after,'new');
    $('facts').textContent='출발 X '+before.start.x.toFixed(2)+' m · Z '+before.start.z.toFixed(2)+' m · 방향 '+(before.start.yaw*180/Math.PI).toFixed(1)+'° · 두 정책 첫 RGB 해시 '+before.firstFrameSHA256.slice(0,12)+' 동일';
    $('live').href='../demo/search.html?scene='+id+'&case='+i;
    $('table').replaceChildren(...group.map(p=>{const tr=document.createElement('tr');for(const label of [names[p.case],status(p.before),status(p.after)]){const td=document.createElement('td');td.textContent=label;tr.append(td);}return tr;}));
  }
  $('layout').onchange=$('trial').onchange=show;show();
}
main().catch(err=>{$('summary').textContent=err.message;});
