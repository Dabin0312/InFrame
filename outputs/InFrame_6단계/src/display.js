'use strict';
const byId = id => document.getElementById(id);
const {cases, floor} = window.InFrame;
const routes = window.InFrameRoutes = Object.create(null);
const policies = [
  {dir:'teacher',name:'지도 교사',color:'#198078'},
  {dir:'one',name:'한 프레임',color:'#a15715'},
  {dir:'four',name:'최근 4스텝',color:'#7954aa'}
];
const reasonText = {success:'성공',timeout:'시간 초과',collision_limit:'충돌 3회',stopped_too_far:'거리 초과 정지',goal_out_of_view:'시야 밖 정지'};
const groupNames = {all:'전체',shared:'공통 실패',four:'4스텝만 성공',one:'한 프레임만 성공',both:'두 학생 성공'};
const state = {group:'all',item:null,track:null,tick:0,choice:0,draw:0,timer:null,selected:2,probe:false};
const images = new Map(), scripts = new Map();
const folder = (item,i) => 'data/'+item.id+'/'+policies[i].dir+'/';
const seconds = t => (t*.25).toFixed(2)+'초';
const meters = d => d.toFixed(2)+' m';
const visible = r => r.seen?'C 확인':'C 미확인';
const runEnd = r => r.stop?'STOP 사진':'강제 종료 사진';
function make(tag,cls,content) {
  const node=document.createElement(tag);
  if(cls)node.className=cls;
  if(content!==undefined)node.textContent=content;
  return node;
}
function image(url) {
  if(!images.has(url)){
    const promise=new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('사진을 열 수 없음: '+url));im.src=url;});
    images.set(url,promise);
    if(images.size>40)images.delete(images.keys().next().value);
  }
  return images.get(url);
}
function getTrace(id) {
  if(routes[id])return Promise.resolve(routes[id]);
  if(!scripts.has(id)){
    scripts.set(id,new Promise((resolve,reject)=>{
      const s=document.createElement('script');s.src='data/'+id+'/trace.js';
      s.onload=()=>resolve(routes[id]);s.onerror=()=>reject(Error('경로 기록을 열 수 없음: '+id));
      document.head.append(s);
    }));
  }
  return scripts.get(id);
}
function fail(error){byId('error').textContent=error.message;byId('error').hidden=false;halt()}
function halt(){clearInterval(state.timer);state.timer=null;byId('play').textContent='▶ 재생'}
function subset(){return cases.filter(c=>state.group==='all'||c.group===state.group)}
const mapView=new ComparisonMap(byId('map'),byId('pins'),floor,id=>{changeGroup('shared',id,true)});
function mapDraw(){
  const scope=byId('scope').value;
  byId('mapNote').textContent=scope==='atlas'?'숫자: 사례 선택 · 두 학생의 사건 위치':state.probe?'연두 점선: 별도 시험한 방향':'··· 교사 전체 경로';
  if(state.track)mapView.update(state.item,state.track,state.tick,scope,state.selected,state.probe);
}
function applyGroup(group,selected){
  state.group=group;
  for(const b of byId('filters').children)b.setAttribute('aria-pressed',String(b.dataset.group===group));
  const options=subset();
  byId('case').replaceChildren(...options.map(c=>new Option(c.id,c.id)));
  byId('shortcuts').replaceChildren();
  if(group==='shared'){
    for(const c of options){
      const b=make('button','case-chip',c.id.slice(-3));b.dataset.id=c.id;b.setAttribute('aria-label',c.id+' 선택');
      b.onclick=()=>select(c.id);byId('shortcuts').append(b);
    }
  }
  return options.some(c=>c.id===selected)?selected:options[0].id;
}
function changeGroup(group,preferred,zoom=false){select(applyGroup(group,preferred),zoom)}
function renderStatic(item){
  byId('caseTitle').textContent=item.id;
  byId('scene').textContent='Skokloster 성  /  목표 소화기 C  /  출발점에서 관측점까지 '+meters(item.initial_distance);
  byId('case').value=item.id;
  byId('teacherStop').textContent='교사 STOP '+item.runs[0].elapsed.toFixed(2)+'초';
  for(const b of byId('shortcuts').children)b.setAttribute('aria-pressed',String(b.dataset.id===item.id));
  for(let i=0;i<3;i++){
    const r=item.runs[i];
    byId('still'+i).src=folder(item,i)+'last.png';byId('still'+i).alt=policies[i].name+' '+runEnd(r);
    byId('stillTag'+i).textContent=runEnd(r);
    const status=make('span','status '+(r.success?'good':'bad'),reasonText[r.reason]);
    byId('endpoint'+i).replaceChildren(status,document.createTextNode(' · '+meters(r.remaining)+' · '+visible(r)));
    byId('timestamp'+i).textContent='0.00초';byId('action'+i).textContent='—';
  }
}
async function select(id,zoom=false){
  halt();const serial=++state.choice;++state.draw;
  state.item=cases.find(c=>c.id===id);state.track=null;state.tick=0;state.selected=2;state.probe=false;
  const item=state.item;
  byId('scope').querySelector('[value="event"]').disabled=item.group!=='shared';
  byId('scope').value=zoom?'event':'room';
  byId('seek').disabled=true;byId('play').disabled=true;
  renderStatic(item);
  byId('detailGrid').replaceChildren();
  try{
    const t=await getTrace(id);if(serial!==state.choice)return;
    state.track=t;byId('seek').max=Math.max(...t.map(x=>x.length))-1;
    byId('seek').disabled=false;byId('play').disabled=false;
    renderDiagnosis();
    if(zoom && item.group==='shared')state.tick=item.diagnoses[state.selected].t;
    await renderTick();
  }catch(e){if(serial===state.choice)fail(e)}
}
function advanceCase(direction){
  const options=subset(),i=options.findIndex(c=>c.id===state.item.id);
  select(options[(i+direction+options.length)%options.length].id);
}
function describeAction(command){
  if(!command)return '강제 종료';
  if(command[2])return 'STOP';
  if(command[0]<.002)return command[1]>0?'좌회전':'우회전';
  return Math.abs(command[1])>.1?'전진·회전':'전진';
}
async function renderTick(){
  if(!state.track)return;
  const token=++state.draw,item=state.item,track=state.track,tick=state.tick;
  byId('seek').value=tick;byId('clock').textContent=(tick*.25).toFixed(2)+' / '+(byId('seek').max*.25).toFixed(2)+' s';
  const steps=track.map(t=>Math.min(tick,t.length-1));
  const frames=await Promise.all(steps.map((n,i)=>image(folder(item,i)+'rgb-'+String(Math.floor(n/64)).padStart(2,'0')+'.jpg')));
  if(token!==state.draw || state.item!==item)return;
  for(let i=0;i<3;i++){
    const n=steps[i],j=n%64,row=track[i][n];
    byId('live'+i).getContext('2d').drawImage(frames[i],(j%8)*192,Math.floor(j/8)*144,192,144,0,0,192,144);
    byId('live'+i).dataset.step=n;
    byId('timestamp'+i).textContent=seconds(n);
    byId('action'+i).textContent=(tick>n?'종료 유지':describeAction(row[3]));
    byId('hits'+i).textContent='충돌 '+row[4]+'회';
  }
  for(const b of byId('detailGrid').querySelectorAll('button[data-step]')){
    b.setAttribute('aria-pressed',String(Number(b.dataset.step)===tick&&Number(b.dataset.policy)===state.selected && (b.dataset.probe==='true')===state.probe));
  }
  mapDraw();
}
function seek(tick){
  if(!state.track)return;
  halt();state.tick=Math.min(Number(byId('seek').max),Math.max(0,Math.round(tick)));
  renderTick().catch(fail);
}
function play(){
  if(!state.track)return;
  if(state.timer){halt();return}
  if(state.tick>=Number(byId('seek').max))state.tick=0;
  renderTick().catch(fail);byId('play').textContent='Ⅱ 일시정지';
  state.timer=setInterval(()=>{
    if(state.tick>=Number(byId('seek').max)){halt();return}
    ++state.tick;renderTick().catch(fail);
  },250/Number(byId('speed').value));
}
function jump(i,t,mode='room',probe=false){
  state.selected=i;state.probe=probe;byId('scope').value=mode;seek(t);
}
function eventButton(i,label,t,mode,probe=false){
  const b=make('button','',label);b.dataset.policy=i;b.dataset.step=t;b.dataset.probe=String(probe);
  b.onclick=()=>jump(i,t,mode,probe);return b;
}
function detailsCard(i,d){
  const r=state.item.runs[i],article=make('article','diagnosis');article.style.setProperty('--c',policies[i].color);
  const head=make('div','detailhead'),actions=make('div','eventbuttons');
  const desc=make('p'),note=make('p','note');
  const kind=d.kind==='turns'?'제자리 회전 반복':'이동 가능 경계에서 충돌';
  head.append(make('b','',policies[i].name+' · '+kind),make('span','loc','X '+d.xyz[0].toFixed(2)+' / Z '+d.xyz[2].toFixed(2)+' m'));
  if(d.kind==='turns'){
    desc.textContent=r.elapsed.toFixed(0)+'초 동안 '+d.commands+'개 명령 중 전진 '+d.forward_commands+'회. 좌우 회전 방향이 '+d.reversals+'번 바뀌어 출발점에서 '+meters(r.distance)+' 이동했다.';
    actions.append(eventButton(i,'반복 확인 '+seconds(d.t),d.t,'event'));
  }else{
    const h=d.contacts[0];
    desc.textContent=seconds(h.t)+' 시점에 첫 충돌. 직전 명령이 요청한 '+(h.requested*100).toFixed(1)+' cm 중 '+(h.moved*100).toFixed(1)+' cm 이동했고, 누적 3회 충돌로 종료됐다.';
    for(let j=0;j<d.contacts.length;j++)actions.append(eventButton(i,'충돌 '+(j+1)+' · '+seconds(d.contacts[j].t),d.contacts[j].t,'event'));
  }
  const alt=d.probe.alternative,turn=alt.turn_deg===0?'그대로':(alt.turn_deg>0?'왼쪽 ':'오른쪽 ')+Math.abs(alt.turn_deg)+'° 회전 후';
  note.textContent='같은 사건 자세에서 별도 시험한 결과, 정면으로 '+(d.probe.straight.reach_m*100).toFixed(0)+' cm, '+turn+' '+(alt.reach_m*100).toFixed(0)+' cm 진행했다.';
  actions.append(eventButton(i,'대안 방향 보기',d.t,'event',true));
  article.append(head,desc,note,actions);return article;
}
function renderDiagnosis(){
  const item=state.item,details=byId('detailGrid');details.replaceChildren();
  if(item.group==='shared'){
    byId('detailTitle').textContent='공통 실패 진단';
    byId('detailHint').textContent='사건을 누르면 세 카메라가 같은 시각으로 이동한다. 지도 좌표 단위는 m.';
    details.append(detailsCard(1,item.diagnoses[1]),detailsCard(2,item.diagnoses[2]));
  }else{
    byId('detailTitle').textContent='종료 비교';
    byId('detailHint').textContent='종료한 정책은 마지막 화면을 유지한다.';
    for(let i=1;i<3;i++){
      const r=item.runs[i],article=make('article','diagnosis');article.style.setProperty('--c',policies[i].color);
      article.append(make('b','',policies[i].name+' · '+reasonText[r.reason]),
        make('p','',meters(r.distance)+' 이동 · 종료 시 관측점까지 '+meters(r.remaining)+' · '+visible(r)+' · '+(r.stop?'STOP 명령':'강제 종료')),
        eventButton(i,'종료 '+r.elapsed.toFixed(2)+'초',state.track[i].length-1,'room'));
      details.append(article);
    }
  }
}
function openPhoto(i){
  const item=state.item,r=item.runs[i];byId('photoTitle').textContent=item.id+' · '+policies[i].name+' '+runEnd(r);
  byId('zoomPhoto').src=folder(item,i)+'last.png';
  byId('photoCaption').textContent=reasonText[r.reason]+' · '+r.elapsed.toFixed(2)+'초 · 관측점까지 '+meters(r.remaining)+' · '+visible(r);
  halt();byId('photo').showModal();
}
function init(){
  policies.forEach((p,i)=>{
    const score=make('span','score');score.style.setProperty('--c',p.color);
    score.append(make('i','dot'),document.createTextNode(p.name),make('strong','',cases.filter(c=>c.runs[i].success).length+'/60'));byId('scores').append(score);
    const feed=make('article','feed');feed.style.setProperty('--c',p.color);
    feed.innerHTML='<div class="feedhead"><h3></h3><small id="timestamp'+i+'"></small></div><div class="live"><canvas width="192" height="144" id="live'+i+'"></canvas><span class="tag">로봇 시점</span></div><div class="metricline"><b id="action'+i+'"></b><span id="hits'+i+'"></span></div><button type="button" class="still"><img id="still'+i+'"><span class="tag" id="stillTag'+i+'"></span></button><div class="endpoint" id="endpoint'+i+'"></div>';
    feed.querySelector('h3').textContent=p.name;const btn=feed.querySelector('button');btn.setAttribute('aria-label',p.name+' 종료 사진 확대');btn.onclick=()=>openPhoto(i);byId('feeds').append(feed);
  });
  for(const [k,label] of Object.entries(groupNames)){
    const n=k==='all'?cases.length:cases.filter(c=>c.group===k).length;if(!n)continue;
    const b=make('button','',label);b.dataset.group=k;b.append(make('span','num',n));
    b.onclick=()=>changeGroup(k,state.item?.id);byId('filters').append(b);
  }
  byId('case').onchange=e=>select(e.target.value);byId('back').onclick=()=>advanceCase(-1);byId('advance').onclick=()=>advanceCase(1);
  byId('scope').onchange=()=>{state.probe=false;mapDraw()};
  byId('play').onclick=play;byId('prev').onclick=()=>seek(state.tick-1);byId('next').onclick=()=>seek(state.tick+1);
  byId('seek').oninput=e=>seek(+e.target.value);byId('last').onclick=()=>seek(+byId('seek').max);
  byId('teacherStop').onclick=()=>seek(state.track[0].length-1);
  byId('speed').onchange=()=>{if(state.timer){halt();play()}};
  byId('closePhoto').onclick=()=>byId('photo').close();
  document.addEventListener('keydown',e=>{
    if(byId('photo').open||['SELECT','INPUT','BUTTON'].includes(e.target.tagName))return;
    if(e.code==='Space'){e.preventDefault();play()}
    if(e.key==='ArrowRight'){e.preventDefault();seek(state.tick+1)}
    if(e.key==='ArrowLeft'){e.preventDefault();seek(state.tick-1)}
  });
  const requested=location.hash.slice(1);
  const first=cases.find(c=>c.id===requested)||cases.find(c=>c.id==='C-val-025');
  changeGroup(first.group==='shared'?'shared':'all',first.id);
}
init();
