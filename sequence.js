import {createScan} from './scan.js';
import {showEpisode,manualMode,leaveMission} from './scene.js';

const el=id=>document.getElementById(id);
const viewer=el('playground'), video=el('indoor'), seek=el('sequence-time'), toggle=el('sequence-play');
const chapters=[...document.querySelectorAll('[data-chapter]')];
const starts=[0,5.5,12], end=21;
const reduce=matchMedia('(prefers-reduced-motion: reduce)');
const descriptions=[
  '카메라가 움직이면 같은 공간을 여러 각도에서 관측합니다.',
  'ORB-SLAM3가 구한 카메라 자세에 깊이 영상을 겹쳐 공간을 복원합니다.',
  '로봇이 지도 기반 경로를 따라 소화기를 찾고, 마지막 시야를 확인합니다.'
];
let scan, current=0, phase=-1, playing=!reduce.matches, manual=false, reversed=false, layer=false;
let visible=false, animation=0, last=null, blocked=false, videoPending=false, lastNav=-1;
function time(s){return '0:'+String(Math.floor(s)).padStart(2,'0')}
function eligible(){return visible && !document.hidden && playing && !manual}
function pausedVideo(){if(!video.paused)video.pause()}
function videoAt(value,force){
  if(video.readyState<1)return;
  const playNow=eligible() && value<starts[2];
  if(!playNow)pausedVideo();
  const wanted=Math.min(value,video.duration-.065);
  if (Math.abs(video.currentTime-wanted) > (playNow && !force ? .18 : .04) && (force || !video.seeking)) {
    video.currentTime=Math.max(0,wanted);
  }
  if(playNow&&video.paused&&!blocked&&!videoPending){
    videoPending=true;video.play().catch(err=>{if(err.name!=='AbortError')blocked=true}).finally(()=>{videoPending=false});
  }
}
function caption(){
  el('sequence-caption').textContent=manual?'원하는 위치에서 정지해 거리와 시야를 확인하세요.':
    phase<2&&layer?'최종 희소 지도점 3,381개 위에 현재 프레임의 카메라 자세를 표시합니다.':
    phase===2&&current>=end?'관측 지점에 도착했습니다. 같은 자리에서 방향을 바꿔 정지 판정을 비교할 수 있습니다.':descriptions[phase];
}
function render(force=false){
  const next=current<starts[1]?0:current<starts[2]?1:2;
  if(next!==phase||force){
    phase=next;viewer.dataset.phase=String(phase);
    chapters.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===phase)));
    el('scan-view').hidden=phase===2;el('mission').hidden=phase!==2;
    el('manual').hidden=phase!==2;el('manual').textContent=manual?'시연으로 돌아가기':'직접 주행';
    el('mission').classList.toggle('manual',manual);el('manual-help').hidden=!manual;
    el('data-source').textContent=phase===2?'Habitat-Sim · 지도 기반 경로':'TUM fr1/xyz · ORB-SLAM3';
    caption();
  }
  if(phase<2){
    const stamp=scan?.seek(current);
    el('camera-time').textContent=stamp===undefined?'':stamp.toFixed(1)+' s';
    videoAt(current,force);
  }else{
    pausedVideo();
    if(!manual){
      const p=Math.min(1,(current-starts[2])/(end-starts[2]));
      if(force||Math.abs(p-lastNav)>.001||p===1){showEpisode(p,reversed);lastNav=p}
    }
  }
  if(phase<2)lastNav=-1;
  const finished=current>=end;
  el('flip').hidden=manual||!finished;
  el('flip').textContent=reversed?'목표 쪽 보기':'뒤돌아보기';
  toggle.classList.toggle('playing',playing&&!manual);toggle.classList.toggle('ended',finished&&!manual);
  toggle.setAttribute('aria-label',playing?'시연 일시정지':finished?'처음부터 다시 재생':'시연 재생');
  toggle.disabled=manual;seek.disabled=manual;
  seek.value=Math.round(current*100);seek.style.setProperty('--progress',(current/end*100)+'%');
  seek.setAttribute('aria-valuetext',time(current)+' / '+time(end));
  el('clock').value=time(current)+' / '+time(end);
}
function schedule(){
  if(eligible()&&!animation)animation=requestAnimationFrame(tick);
}
function tick(now){
  animation=0;if(!eligible()){last=null;pausedVideo();return}
  if(last!==null)current=Math.min(end,current+Math.min(.15,(now-last)/1000));
  last=now;
  if(current>=end){playing=false;last=null;render(true);return}
  render();schedule();
}
function setTime(value,run){
  if(manual){manual=false;leaveMission()}
  current=Math.max(0,Math.min(end,value));playing=run&&current<end;last=null;reversed=false;blocked=false;render(true);schedule();
}
toggle.onclick=()=>{if(!playing&&current>=end)setTime(0,true);else setTime(current,!playing)};
seek.oninput=()=>setTime(Number(seek.value)/100,false);
chapters.forEach((btn,i)=>btn.onclick=()=>setTime(starts[i],true));
el('manual').onclick=()=>{
  if(manual){setTime(current,false);return}
  manual=true;playing=false;pausedVideo();render(true);manualMode();
};
el('flip').onclick=()=>{reversed=!reversed;render(true)};
createScan(el('scan-canvas'),el('map-layer'),value=>{layer=value;caption()})
  .then(result=>{scan=result;render(true)})
  .catch(()=>{el('map-layer').hidden=true;el('scan-canvas').replaceWith(Object.assign(new Image(),{src:'tracking.svg',alt:'ORB-SLAM3 카메라 궤적과 지도점',className:'map-poster'}))});
video.addEventListener('loadedmetadata',()=>render(true));
video.addEventListener('error',()=>{blocked=true;video.poster='indoor.jpg';});
new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;last=null;if(!visible)pausedVideo();else{render();schedule()}},{threshold:.08}).observe(viewer);
document.addEventListener('visibilitychange',()=>{last=null;if(document.hidden)pausedVideo();else{render();schedule()}});
reduce.addEventListener('change',()=>{if(reduce.matches)setTime(current,false)});
render(true);
