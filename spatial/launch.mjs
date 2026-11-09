import {goals} from './goals.mjs';
import {startMap} from './start-map.mjs';

const el = id => document.getElementById(id);
const launch = el('launch'), presets = el('start-id'), heading = el('heading');
const status = el('picked-position');
async function setup() {
  const response = await fetch(new URL('floor.json', import.meta.url));
  if (!response.ok) throw Error('출발 지도를 불러올 수 없습니다.');
  const floor = await response.json();
  floor.starts.forEach((s,i) => presets.add(new Option(s.id,i)));
  const custom = new Option('직접 선택','custom');
  custom.disabled = true; presets.add(custom);
  let selected, runtime, preparing, pending = false;
  const map = startMap(el('start-map'), floor, xyz => {
    select({id:'custom', xyz, yaw:heading.value==='recorded' ? 0 : Number(heading.value)}, 'custom');
  }, () => {
    status.textContent = '물체나 주행 경계 바깥에서는 출발할 수 없어요. 색이 칠해진 바닥을 선택하세요.';
  });
  function select(start, choice) {
    selected = start;
    if(choice!=='custom') heading.value='recorded';
    else if(heading.value==='recorded') heading.value='0';
    el('preset-heading').disabled=choice==='custom';
    presets.value = choice;
    map.select(start);
    const [x,,z] = start.xyz;
    status.textContent = 'X '+x.toFixed(2)+' m　 Z '+z.toFixed(2)+' m';
    if (runtime) {
      launch.hidden = false;
      launch.querySelector('strong').textContent = '▶　여기서 주행';
      runtime.preview();
    }
  }
  async function prepare(){
    if(runtime) return runtime;
    if(!preparing) {
      preparing=import('./live.mjs').then(({init})=>init(floor,()=>selected,map.pose))
        .then(scene=>{runtime=scene;return scene;}).catch(error=>{preparing=null;throw error;});
    }
    return preparing;
  }
  const goalMenu=el('live-goal'),mode=el('live-mode');
  function changeGoal(){
    const key=goalMenu.value,g=goals[key];
    if(key!=='extinguisher')mode.value='map';
    mode.options[1].disabled=key!=='extinguisher';
    map.highlight(key);el('goal-legend').textContent=g.label+' '+g.id;
    el('policy-name').textContent=mode.value==='h4'?'H4 STUDENT POLICY':'SEMANTIC MAP + RGB';
    if(runtime){launch.hidden=false;launch.querySelector('strong').textContent='▶　여기서 주행';runtime.preview();}
  }
  goalMenu.onchange=mode.onchange=changeGoal;changeGoal();
  presets.onchange = () => select(floor.starts[Number(presets.value)],presets.value);
  heading.onchange = () => select({id:'custom',xyz:selected.xyz,yaw:Number(heading.value)},'custom');
  select(floor.starts[0],'0');
  launch.classList.add('ready-preview');
  launch.disabled = false;
  // Show the camera at the chosen pose as soon as the demo comes into view.
  const observer=new IntersectionObserver(entries=>{
    if(!entries.some(e=>e.isIntersecting)) return;
    observer.disconnect();
    prepare().catch(error=>{el('live-state').textContent=error.message;});
  },{rootMargin:'150px'});
  observer.observe(launch);
  launch.onclick = async () => {
    if (pending) return;
    pending = true;
    launch.querySelector('strong').textContent = '정책을 불러오는 중…';
    try {
      const scene=await prepare();
      scene.reset();
      launch.hidden = true;
    } catch (error) {
      el('live-state').textContent = error.message;
      launch.querySelector('strong').textContent = '다시 열기';
    } finally { pending = false; }
  };
}
setup().catch(error => { status.textContent = error.message; });
