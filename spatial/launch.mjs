const launch=document.querySelector('#launch'),sel=document.querySelector('#start-id');
const floor=await fetch(new URL('./floor.json',import.meta.url)).then(r=>r.json());
floor.starts.forEach((s,i)=>sel.add(new Option(s.id,i)));
let loading=false;
launch.onclick=async()=>{
  if(loading)return;loading=true;launch.querySelector('strong').textContent='장면과 정책을 불러오는 중…';
  try{const {init}=await import('./live.mjs');await init(floor);launch.hidden=true;}
  catch(e){document.querySelector('#live-state').textContent=String(e.message);launch.querySelector('strong').textContent='다시 열기';}
  finally{loading=false;}
};
