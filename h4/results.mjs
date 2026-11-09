const $=id=>document.getElementById(id),seconds=t=>t.toFixed(2)+' s';
const answer=await fetch('results.json');
if(!answer.ok)throw Error('검증 기록을 불러올 수 없습니다.');
const data=await answer.json(), cases=data.cases;
const counts=key=>[cases.filter(c=>c[key]?.valid).length,cases.filter(c=>!c.windows.length&&c[key]).length];
const [b0,f0]=counts('before'),[b1,f1]=counts('stop'),n=cases.filter(c=>c.windows.length).length;
$('hits').textContent=b0+' / '+n+' → '+b1+' / '+n;$('false').textContent=f0+' / '+(cases.length-n)+' → '+f1+' / '+(cases.length-n);
for(const c of cases)$('case').add(new Option(c.name,c.id));
let current;
function panel(id,event){
  const el=$(id);el.replaceChildren();$(id+'-time').textContent=event?seconds(event.t):'';
  if(event){const img=new Image();img.alt='정지 행동이 출력된 순간의 RGB 입력';img.src=event.photo;el.append(img);}
  else{const label=document.createElement('span');label.className='absent';label.textContent='STOP 없음';el.append(label);}
  $(id+'-note').textContent=event?(event.valid?'판독 구간 안에서 정지':'판독 구간 밖에서 정지')+' · '+(event.p?'카메라 위치 추적됨':'정지 위치 미확정'):'영상 끝까지 정지 명령 없음';
}
function draw(){
  const seg=Number($('seg').value),c=current,can=$('trajectory'),g=can.getContext('2d'),W=can.width,H=can.height;
  g.clearRect(0,0,W,H);
  const frames=c.path.filter(r=>r[0]===seg),track=frames.filter(r=>r.length===3).map(r=>r.slice(1));
  const points=c.points.filter(r=>r[0]===seg).map(r=>r.slice(1)),targets=c.targets.filter(r=>r[0]===seg);
  $('mapkey').textContent='초록 선 · 카메라 동선　● 소화기 추정점　□ 개선 H4 STOP';
  if(!track.length){g.fillStyle='#58665b';g.font='20px sans-serif';g.textAlign='center';g.fillText('이 구간의 카메라 위치 미확정',W/2,H/2);return;}
  const ranges=[0,1].map(k=>{const a=points.map(p=>p[k]).sort((v,w)=>v-w),core=track.map(p=>p[k]).concat(targets.map(t=>t[1+k]));if(a.length)core.push(a[Math.floor(.05*a.length)],a[Math.floor(.95*a.length)]);return [Math.min(...core),Math.max(...core)];});
  const scale=Math.min((W-84)/Math.max(.02,ranges[0][1]-ranges[0][0]),(H-82)/Math.max(.02,ranges[1][1]-ranges[1][0]));
  const xy=p=>p.map((x,i)=>(i?H:W)/2+scale*(x-(ranges[i][0]+ranges[i][1])/2));
  for(const p of points){const [x,y]=xy(p);g.fillStyle='#a8b5a6';g.fillRect(x-1.5,y-1.5,3,3);}
  let connected=false;g.beginPath();for(const r of frames){if(r.length!==3){connected=false;continue;}const p=xy(r.slice(1));if(connected)g.lineTo(...p);else g.moveTo(...p);connected=true;}g.strokeStyle='#477b54';g.lineWidth=3;g.stroke();
  g.textAlign='left';g.font='bold 17px sans-serif';
  for(const t of targets){const [x,y]=xy(t.slice(1,3));g.fillStyle='#ad4728';g.beginPath();g.arc(x,y,6,0,Math.PI*2);g.fill();g.fillText('E'+t[3],x+8,y-8);}
  for(const [e,color,label] of [[c.before,'#4a6290','기존'],[c.stop,'#91530f','STOP']]){
    if(e?.seg!==seg||!e.p)continue;const [x,y]=xy(e.p);g.lineWidth=3;g.strokeStyle=color;g.strokeRect(x-8,y-8,16,16);g.fillStyle=color;g.fillText(label,x+11,y+18);
  }
}
function show(){
  current=cases.find(c=>c.id===$('case').value);const c=current;
  panel('old',c.before);panel('new',c.stop);
  $('reference').src=c.refPhoto;$('ref-time').textContent=seconds(c.reference);
  $('window').textContent=c.windows.length?'소화기 본체 확인\n'+c.windows.map(([a,b])=>seconds(a)+' – '+seconds(b)).join('\n'):'판독 가능한 소화기 본체 없음';
  $('source').href=c.url;$('seg').replaceChildren();
  for(const j of c.segments)$('seg').add(new Option('지도 '+j,j));
  $('seg').value=c.stop?.seg??c.before?.seg??c.referenceSeg;draw();
  const url=new URL(location.href);url.searchParams.set('case',c.id);history.replaceState(null,'',url);
}
const key=new URLSearchParams(location.search).get('case');$('case').value=cases.some(c=>c.id===key)?key:'fe75cd3028c834ef';show();
$('case').onchange=show;$('seg').onchange=draw;
