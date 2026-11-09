import { start, target, observation, obstacles, reference, pathLength, sampleReference, canStand, pathTo, move, seesTarget, distance, heading, clamp, angleDelta } from './navigation.js';
import { CanvasWorld } from './fallback.js';

const $ = id => document.getElementById(id);
const stage = $('stage'), mini = $('minimap'), slider = $('time');
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const recordedRoute = reference.map(([x,,z]) => ({x,z}));
const state = {
  pose:{...start}, eye:false, pitch:-.14, mapAngle:0, routePoints:null,
  mode:'free', progress:0, playing:false, reversed:false
};
let panelWidth=1, panelHeight=1, inView=true, frame=0, lastTime=null;
let waypoints=[], faceGoal=false, destination=null, lastPointer=null, turning=0;
let stickX=0,stickForward=0,lastCoord='',messageTimer;
const keys=new Set();
const stick=$('stick'),thumb=stick.querySelector('i');
const touchPad=document.querySelector('.touch-controls');

// Draw immediately and keep the same inputs, path and pose when accelerated 3D becomes ready.
let activeCanvas=$('map'), world=new CanvasWorld(activeCanvas);
function resize(){
  const rect=stage.getBoundingClientRect();panelWidth=rect.width;panelHeight=rect.height;
  if(!panelWidth || !panelHeight)return;
  world.resize(panelWidth,panelHeight,devicePixelRatio||1); paint();
}
function useSoftwareCanvas(){
  const replacement=document.createElement('canvas');replacement.id='map';
  replacement.setAttribute('aria-label',activeCanvas.getAttribute('aria-label'));
  activeCanvas.replaceWith(replacement);activeCanvas=replacement;
  world=new CanvasWorld(activeCanvas);resize();
}
async function loadWorld(){
  try {
    const {World}=await import('./world.js');
    const next=document.createElement('canvas');next.id='map';
    next.setAttribute('aria-label',activeCanvas.getAttribute('aria-label'));
    const accelerated=new World(next);
    activeCanvas.replaceWith(next);activeCanvas=next;world=accelerated;
    next.addEventListener('webglcontextlost',event=>{event.preventDefault();useSoftwareCanvas();},{once:true});
    resize();
    if(!motionPreference.matches && !userInteracted){introStart=performance.now();requestFrame();}
  } catch { /* The playable canvas map is already active on WebGL-limited devices. */ }
}
function setPressed(id,value){$(id).setAttribute('aria-pressed',String(value))}
function showMessage(text,success=false){
  clearTimeout(messageTimer);
  const panel=$('message');
  panel.hidden=false;panel.textContent=text;panel.classList.toggle('success',success);
  messageTimer=setTimeout(()=>{panel.hidden=true},3600);
}
function dismiss(){clearTimeout(messageTimer);$('message').hidden=true}
function clearPath(){waypoints=[];state.routePoints=null;destination=null;faceGoal=false}
function releaseInputs(){
  keys.clear();stickX=0;stickForward=0;turning=0;lastPointer=null;
  thumb.style.transform='';lastTime=null;
}
function horizontalFov(){return 2*Math.atan(Math.tan(88*Math.PI/360)*panelWidth/panelHeight)}
function visibleGoal(){return seesTarget(state.pose,horizontalFov(),88*Math.PI/180,state.pitch)}
function drawMini(){
  const c=mini.getContext('2d'),size=mini.width;
  const pixel=n=>size*(.08+(n+4)*.105);
  c.clearRect(0,0,size,size);
  c.fillStyle='#dadcf7';c.fillRect(pixel(-4),pixel(-4),size*.84,size*.84);
  for(const ob of obstacles.slice(0,2)){
    c.fillStyle='#979dca';
    c.fillRect(pixel(ob.x-ob.width/2),pixel(ob.z-ob.depth/2),size*.105*ob.width,size*.105*ob.depth);
  }
  c.fillStyle='#ed4944';c.beginPath();c.arc(pixel(target.x),pixel(target.z),5,0,2*Math.PI);c.fill();
  const {pose}=state;c.save();c.translate(pixel(pose.x),pixel(pose.z));c.rotate(pose.yaw);
  c.fillStyle='#625bf52c';c.beginPath();c.moveTo(0,0);c.arc(0,0,27,-2.15,-.99);c.closePath();c.fill();
  c.fillStyle='#3d32bb';c.beginPath();c.moveTo(0,-10);c.lineTo(6,6);c.lineTo(-6,6);c.closePath();c.fill();c.restore();
}
function paint(){
  if(!panelWidth || !panelHeight)return;
  const label=world.render(state);
  const tag=$('target-tag');
  tag.hidden=state.eye||!label;
  if(!tag.hidden){tag.style.left=label.x+'px';tag.style.top=(label.y-11)+'px'}
  const player=$('player-tag');
  player.hidden=tag.hidden || distance(state.pose,target)<1.05;
  if(!player.hidden){player.style.left=label.player[0]+'px';player.style.top=(label.player[1]+9)+'px'}
  if(state.eye)drawMini();
  const signed=n=>(n>=0?'+':'−')+Math.abs(n).toFixed(2);
  const coords='X '+signed(state.pose.x)+'  /  Z '+signed(state.pose.z)+' m';
  if(coords!==lastCoord){$('coordinates').textContent=coords;lastCoord=coords}
  if(state.mode==='free')return;
  slider.value=Math.round(state.progress*1000);
  const read=(Math.min(1,state.progress/.86)*pathLength).toFixed(2);
  $('replay-distance').value=read+' / 8.19 m';
  slider.setAttribute('aria-valuetext',read+'미터');
  if(!$('compare').hidden)$('compare-result').value=visibleGoal()?'시야 안':'시야 밖';
}
function sync(){
  const free=state.mode==='free';
  stage.classList.toggle('eye',state.eye);
  mini.hidden=!state.eye;$('crosshair').hidden=!state.eye;
  setPressed('overview',!state.eye);setPressed('first-person',state.eye);
  setPressed('free',free);setPressed('auto',!free);
  setPressed('toward',!state.reversed);setPressed('away',state.reversed);
  $('replay').hidden=free;touchPad.hidden=!free;
  $('compare').hidden=free||!state.eye||state.progress<1;
  const play=$('play');play.textContent=state.playing?'Ⅱ':'▷';
  play.setAttribute('aria-label',state.playing?'경로 일시정지':'경로 재생');
  paint();
}
function focusStage(){stage.focus({preventScroll:true})}
let userInteracted=false,introStart=null;
function interact(){userInteracted=true;introStart=null}
function changeView(eye){
  interact();state.eye=eye;dismiss();sync();focusStage();
}
function takeControl(){
  interact();dismiss();
  if(state.mode!=='free'){
    state.mode='free';state.playing=false;clearPath();sync();
  }
}
function halt(){
  releaseInputs();clearPath();state.playing=false;
}
function settleReplay(){
  state.pose=sampleReference(state.progress,state.reversed);
  const turn=clamp((state.progress-.86)/.14,0,1);
  state.pitch=-.12-turn*(state.reversed?0:.30);
}
function replay(pos=0,playing=true){
  interact();halt();dismiss();
  state.mode='auto';state.progress=pos;state.playing=playing;state.reversed=false;
  state.routePoints=recordedRoute;settleReplay();sync();requestFrame();
}
function selectGoal(x,z,aim){
  const position=aim?observation:{x,z};
  if(!canStand(position.x,position.z)){showMessage('빈 바닥을 눌러 주세요.');return}
  const path=pathTo(state.pose,position);
  if(!path.length){showMessage('그 지점까지 이동할 수 없어요.');return}
  clearPath();waypoints=path.slice();faceGoal=aim;destination={...position};
  state.routePoints=[{x:state.pose.x,z:state.pose.z},...path];requestFrame();
}
function walkPath(dt){
  let budget=dt*1.65;
  while(waypoints.length && budget>0){
    const next=waypoints[0],pose=state.pose,dist=distance(pose,next);
    if(dist<.01){
      move(pose,next.x-pose.x,next.z-pose.z);
      waypoints.shift();continue;
    }
    const step=Math.min(dist,budget),yaw=heading(pose,next);
    pose.yaw+=angleDelta(pose.yaw,yaw)*Math.min(1,dt*10);
    const used=move(pose,(next.x-pose.x)/dist*step,(next.z-pose.z)/dist*step);
    if(used<step*.5){clearPath();return}
    budget-=step;
    if(step>=dist-.001)waypoints.shift();
  }
  if(!waypoints.length && destination){
    if(faceGoal){
      state.pose.yaw=heading(state.pose,target);
      state.pitch=-.43;
    }
    clearPath();
  }
}
function manualMotion(dt){
  const pressed=code=>keys.has(code)?1:0;
  const forward=pressed('KeyW')+pressed('ArrowUp')-pressed('KeyS')-pressed('ArrowDown')+stickForward;
  const side=pressed('KeyD')-pressed('KeyA')+stickX;
  const turn=pressed('ArrowRight')+pressed('KeyE')-pressed('ArrowLeft')-pressed('KeyQ')+turning;
  state.pose.yaw+=turn*dt*2.25;
  const norm=Math.max(1,Math.hypot(forward,side));
  const pace=dt*1.65/norm,sin=Math.sin(state.pose.yaw),cos=Math.cos(state.pose.yaw);
  move(state.pose,pace*(forward*sin+side*cos),pace*(-forward*cos+side*sin));
}
function requestFrame(){
  if(!frame && inView && !document.hidden)frame=requestAnimationFrame(stepFrame);
}
function stepFrame(now){
  frame=0;if(document.hidden||!inView){lastTime=null;return}
  const dt=lastTime===null?1/60:clamp((now-lastTime)/1000,0,.045);lastTime=now;
  let again=false;
  if(introStart!==null){
    const t=clamp((now-introStart)/1100,0,1);state.mapAngle=(1-t)**3*.14;
    if(t===1)introStart=null;else again=true;
  }
  if(state.playing){
    state.progress=clamp(state.progress+dt/8.8,0,1);settleReplay();
    if(state.progress>=1){state.playing=false;sync()}else again=true;
  }else if(waypoints.length){walkPath(dt);again=waypoints.length>0}
  else if(keys.size || stickForward || stickX || turning){manualMotion(dt);again=true}
  paint();if(again)requestFrame();else lastTime=null;
}
$('target-tag').onclick=()=>{takeControl();focusStage();selectGoal(target.x,target.z,true)};
$('free').onclick=()=>{takeControl();focusStage()};
$('auto').onclick=()=>{replay(0,true);focusStage()};
$('reset').onclick=()=>{
  interact();halt();dismiss();state.mode='free';state.pose={...start};state.pitch=-.14;
  state.mapAngle=0;state.progress=0;state.reversed=false;sync();focusStage();
};
$('judge').onclick=()=>{
  interact();halt();const visible=visibleGoal(),near=distance(state.pose,observation)<=.8;
  let text='관측 지점까지 '+distance(state.pose,observation).toFixed(1)+' m · 더 가까이 이동하세요.';
  if(near)text=visible?'성공 · 소화기가 정지 화면에 보입니다.':'정지 · 소화기가 보이도록 방향을 돌려 보세요.';
  state.eye=true;sync();showMessage(text,near&&visible);focusStage();
};
$('overview').onclick=()=>changeView(false);$('first-person').onclick=()=>changeView(true);
$('play').onclick=()=>{if(state.progress>=1)replay();else{state.playing=!state.playing;sync();requestFrame()}};
slider.oninput=()=>{state.playing=false;state.progress=Number(slider.value)/1000;state.reversed=false;settleReplay();sync()};
$('ending').onclick=()=>{state.eye=true;replay(1,false)};
for(const [id,reversed] of [['toward',false],['away',true]]){
  $(id).onclick=()=>{state.reversed=reversed;settleReplay();sync()};
}

const movementKeys=new Set(['KeyW','KeyS','KeyA','KeyD','KeyQ','KeyE','ArrowUp','ArrowDown','ArrowLeft','ArrowRight']);
window.addEventListener('keydown',event=>{
  if(!inView || event.ctrlKey||event.altKey||event.metaKey||!movementKeys.has(event.code))return;
  if(document.activeElement!==stage && !(document.activeElement===document.body && event.code.startsWith('Key')))return;
  event.preventDefault();takeControl();clearPath();focusStage();
  if(!keys.has(event.code)){keys.add(event.code);manualMotion(1/60);paint()}
  requestFrame();
});
window.addEventListener('keyup',event=>keys.delete(event.code));
stage.addEventListener('blur',releaseInputs);
window.addEventListener('blur',releaseInputs);
document.addEventListener('visibilitychange',()=>{releaseInputs();if(!document.hidden)requestFrame()});
stage.addEventListener('pointerdown',event=>{
  if(event.button!==0 || event.target!==activeCanvas)return;
  interact();focusStage();dismiss();
  lastPointer={id:event.pointerId,x:event.clientX,y:event.clientY,lastX:event.clientX,lastY:event.clientY,drag:false};
  activeCanvas.setPointerCapture(event.pointerId);
});
stage.addEventListener('pointermove',event=>{
  const p=lastPointer;if(!p || event.pointerId!==p.id)return;
  if(Math.hypot(event.clientX-p.x,event.clientY-p.y)>5)p.drag=true;
  if(p.drag){
    const dx=event.clientX-p.lastX,dy=event.clientY-p.lastY;
    if(state.eye){takeControl();clearPath();state.pose.yaw+=dx*.007;state.pitch=clamp(state.pitch-dy*.005,-.98,.85)}
    else{state.mapAngle=clamp(state.mapAngle-dx*.004,-.43,.58)}
    paint();
  }
  p.lastX=event.clientX;p.lastY=event.clientY;
});
stage.addEventListener('pointerup',event=>{
  const p=lastPointer;if(!p||event.pointerId!==p.id)return;lastPointer=null;
  if(p.drag||state.eye)return;
  const rect=stage.getBoundingClientRect(),nx=(event.clientX-rect.left)/rect.width*2-1,ny=1-(event.clientY-rect.top)/rect.height*2;
  takeControl();
  const floor=world.floorPoint(nx,ny);if(!floor)return;
  const aim=world.hitGoal(nx,ny)||distance(floor,target)<.46;
  if(!aim&&(Math.abs(floor.x)>4 || Math.abs(floor.z)>4))return;
  selectGoal(floor.x,floor.z,aim);
});
stage.addEventListener('pointercancel',()=>{lastPointer=null});
let stickPointer=null;
function moveStick(event){
  const r=stick.getBoundingClientRect(),dx=event.clientX-r.left-r.width/2,dy=event.clientY-r.top-r.height/2;
  const limit=r.width*.31,len=Math.max(limit,Math.hypot(dx,dy));stickX=dx/len;stickForward=-dy/len;
  thumb.style.transform='translate('+stickX*limit+'px,'+(-stickForward*limit)+'px)';requestFrame();
}
stick.onpointerdown=event=>{
  event.preventDefault();takeControl();clearPath();focusStage();stickPointer=event.pointerId;
  stick.setPointerCapture(event.pointerId);moveStick(event);manualMotion(1/60);paint();
};
stick.onpointermove=event=>{if(stickPointer===event.pointerId)moveStick(event)};
function releaseStick(){stickPointer=null;stickX=stickForward=0;thumb.style.transform=''}
stick.onlostpointercapture=releaseStick;stick.onpointercancel=releaseStick;stick.onpointerup=releaseStick;
for(const button of document.querySelectorAll('[data-turn]')){
  button.onpointerdown=event=>{
    event.preventDefault();takeControl();clearPath();focusStage();button.setPointerCapture(event.pointerId);
    turning=Number(button.dataset.turn);state.pose.yaw+=turning*.06;paint();requestFrame();
  };
  button.onpointerup=button.onpointercancel=button.onlostpointercapture=()=>{turning=0};
  button.onclick=event=>{if(event.detail===0){takeControl();clearPath();state.pose.yaw+=Number(button.dataset.turn)*.20;paint()}};
}
new ResizeObserver(resize).observe(stage);
new IntersectionObserver(([entry])=>{
  inView=entry.isIntersecting;lastTime=null;
  if(inView)requestFrame();else releaseInputs();
}).observe(stage);
resize();sync();loadWorld();
