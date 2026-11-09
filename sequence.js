import {createScan} from './scan.js?room=1';
import {manualMode,leaveMission} from './scene.js?room=1';
import {episode} from './episode.js';
import {drive} from './drive-data.js';

const el=id=>document.getElementById(id);
const viewer=el('playground'), survey=el('indoor'), journey=el('drive-video'), opposite=el('reverse-view');
const seek=el('sequence-time'), toggle=el('sequence-play'), badge=el('decision'), box=el('object-box');
const chapters=[...document.querySelectorAll('[data-chapter]')], starts=[0,5.5,12], end=21;
const reduce=matchMedia('(prefers-reduced-motion: reduce)');
const captions=[
  '카메라가 작업대를 돌아 이동하며 바닥과 장애물, 소화기를 관측합니다.',
  '같은 영상에서 추정한 카메라 자세로 깊이를 겹치고 소화기의 위치를 지도에 기록합니다.',
  '로봇이 관측된 바닥으로 경로를 잡아, 지도에 기록한 소화기로 이동합니다.'
];
const frames=drive.frames, stop=frames.at(-1), distance=drive.stopDistance.toFixed(2);
if(drive.scene!==episode.scene)throw Error('Navigation and mapping episodes do not match');
let scan, current=0, phase=-1, playing=!reduce.matches, manual=false, reversed=false, layer=false;
let visible=false, animation=0, last=null, lastSample=null, lastStatus='';
const mediaState=new Map([survey,journey].map(v=>[v,{pending:false,blocked:false}]));

el('metric-frames').innerHTML=episode.frameCount+' <small>/ '+episode.frameCount+' 프레임</small>';
el('metric-distance').innerHTML=episode.pathLength.toFixed(2)+' <small>m</small>';
el('tracking-detail').textContent='희소 지도점 '+episode.landmarks.toLocaleString('ko-KR')+'개. 추정 궤적의 위치 오차(RMSE) '+(episode.trackingRMSE*100).toFixed(1)+' cm.';
el('stop-detail').textContent='소화기에서 '+distance+' m 떨어져 정지. 마지막 RGB-D 영상에서 지도 속 소화기와 일치한 픽셀 '+stop.pixels.toLocaleString('ko-KR')+'개.';
function time(s){return '0:'+String(Math.floor(s)).padStart(2,'0')}
function eligible(){return visible&&!document.hidden&&playing&&!manual}
function pauseMedia(){survey.pause();journey.pause()}
function mediaAt(video,value,force){
  if(video.readyState<1)return;
  const allowed=eligible(), state=mediaState.get(video);
  if(!allowed&&!video.paused)video.pause();
  const target=Math.max(0,Math.min(value,video.duration-.024));
  if(Math.abs(video.currentTime-target)>(allowed && !force ? .12 : .021)&&(force||!video.seeking))video.currentTime=target;
  if(allowed&&video.paused&&!state.blocked&&!state.pending){
    state.pending=true;video.play().catch(err=>{if(err.name!=='AbortError')state.blocked=true}).finally(()=>{state.pending=false});
  }
}
function caption(){
  let text=captions[phase];
  if(manual)text='같은 점유 지도에서 직접 움직이며 목표까지의 거리와 시야를 확인하세요.';
  else if(phase===2&&current>=end)text=reversed?'위치는 그대로입니다. 반대 방향 영상에서는 지도 속 소화기가 관측되지 않습니다.':'지도 속 소화기까지 '+distance+' m. 마지막 카메라 영상에서도 같은 소화기를 확인해 정지했습니다.';
  else if(layer&&phase<2)text='ORB-SLAM3의 최종 희소 지도 위에 이 프레임의 카메라 위치와 방향을 표시합니다.';
  el('sequence-caption').textContent=text;
}
function renderBox(){
  const region=journey.parentElement, rect=lastSample?.box;
  box.hidden=phase!==2||manual||reversed||!rect;
  if(box.hidden)return;
  const {width,height}=region.getBoundingClientRect(),scale=Math.min(width/512,height/384);
  const [left,top,right,bottom]=rect;
  Object.assign(box.style,{left:((width-scale*512)/2+left*scale)+'px',top:((height-scale*384)/2+top*scale)+'px',width:((right-left+1)*scale)+'px',height:((bottom-top+1)*scale)+'px'});
}
function showSample(t){
  const index=Math.min(frames.length-1,Math.floor(t/(end-starts[2])*frames.length));
  const pose=frames[index], finished=pose.action==='STOP';
  if(lastSample!==pose){lastSample=pose;renderBox()}
  const pixels=reversed?drive.oppositePixels:pose.pixels;
  const success=finished&&drive.stopDistance<=.8&&pixels>=15;
  const message=finished?(success?'STOP · 소화기 시야 안':'STOP · 소화기 시야 밖'):(pixels>=15?'소화기 관측':'소화기 탐색');
  if(lastStatus!==message){badge.textContent=message;lastStatus=message}
  badge.classList.toggle('success',success);badge.classList.toggle('miss',finished&&!success);
  el('camera-time').textContent=finished?distance+' m':'';
  scan?.navigate(reversed?{...pose,yaw:pose.yaw+Math.PI}:pose);
}
function render(force=false){
  const next=current<starts[1]?0:current<starts[2]?1:2, finished=current>=end;
  if(next!==phase||force){
    phase=next;viewer.dataset.phase=String(phase);
    chapters.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===phase)));
    el('scan-view').hidden=manual;el('mission').hidden=!manual;
    el('manual').hidden=phase!==2;el('manual').textContent=manual?'시연으로 돌아가기':'직접 주행';
    el('mission').classList.toggle('manual',manual);el('manual-help').hidden=!manual;
    survey.hidden=phase===2;journey.hidden=phase!==2||reversed||finished;opposite.hidden=phase!==2||!finished;
    if(!opposite.hidden){opposite.src=reversed?'reverse.jpg':'stop.jpg';opposite.alt=reversed?'같은 정지 위치에서 뒤돌아본 영상':'지도에서 찾은 소화기가 보이는 실제 정지 프레임'}
    el('feed-name').textContent=phase===2?'로봇 카메라':'실내 카메라';
    el('map-key').textContent=phase===2?'로봇 경로':'촬영 궤적';
    badge.hidden=phase!==2||manual;el('map-flip').hidden=!finished||manual;
    el('map-flip').textContent=reversed?'목표 쪽 보기':'뒤돌아보기';
    if(phase<2)journey.pause();else survey.pause();
    caption();renderBox();
  }
  if(!manual&&phase<2){
    const stamp=scan?.seek(current);el('camera-time').textContent=stamp===undefined?'':stamp.toFixed(1)+' s';
    mediaAt(survey,current,force);
  }else if(!manual){
    const t=current-starts[2];showSample(t);
    if(finished)journey.pause();else mediaAt(journey,t,force);
  }
  toggle.classList.toggle('playing',playing&&!manual);toggle.classList.toggle('ended',finished&&!manual);
  toggle.setAttribute('aria-label',playing?'시연 일시정지':finished?'처음부터 다시 재생':'시연 재생');
  toggle.disabled=manual;seek.disabled=manual;seek.value=Math.round(current*100);
  seek.style.setProperty('--progress',(current/end*100)+'%');seek.setAttribute('aria-valuetext',time(current)+' / '+time(end));el('clock').value=time(current)+' / '+time(end);
}
function schedule(){if(eligible()&&!animation)animation=requestAnimationFrame(tick)}
function tick(now){
  animation=0;if(!eligible()){last=null;pauseMedia();return}
  if(last!==null)current=Math.min(end,current+Math.min(.15,(now-last)/1000));
  last=now;
  if(current>=end){playing=false;last=null;render(true);return}
  render();schedule();
}
function setTime(value,run){
  if(manual){manual=false;leaveMission()}
  current=Math.max(0,Math.min(end,value));playing=run&&current<end;last=null;reversed=false;
  mediaState.forEach(state=>state.blocked=false);render(true);schedule();
}
toggle.onclick=()=>{if(!playing&&current>=end)setTime(0,true);else setTime(current,!playing)};
seek.oninput=()=>setTime(Number(seek.value)/100,false);
chapters.forEach((btn,i)=>btn.onclick=()=>setTime(starts[i],true));
el('manual').onclick=()=>{
  if(manual){setTime(current,false);return}
  manual=true;playing=false;pauseMedia();render(true);manualMode();
};
el('map-flip').onclick=()=>{reversed=!reversed;render(true)};
createScan(el('scan-canvas'),el('map-layer'),value=>{layer=value;caption()})
  .then(result=>{scan=result;render(true)})
  .catch(()=>{el('map-layer').hidden=true;el('scan-canvas').replaceWith(Object.assign(new Image(),{src:'plan.svg?room=1',alt:'이 작업실의 관측 격자와 주행 경로',className:'map-poster'}))});
for(const video of [survey,journey])video.addEventListener('loadedmetadata',()=>render(true));
new ResizeObserver(renderBox).observe(journey.parentElement);
new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;last=null;if(!visible)pauseMedia();else{render();schedule()}},{threshold:.08}).observe(viewer);
document.addEventListener('visibilitychange',()=>{last=null;if(document.hidden)pauseMedia();else{render();schedule()}});
reduce.addEventListener('change',()=>{if(reduce.matches)setTime(current,false)});
render(true);
