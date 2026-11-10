import {castle,canonical,categories,prompts,actions} from './castle.mjs';
import {ask} from '../spatial/rpc.mjs';
const starts={
  gallery:{x:2.35,z:12.0,yaw:0},
  fresh:{x:6.320837020874023,z:8.613851547241211,yaw:.4983935122352515},
  transfer:{x:2.1,z:19.2,yaw:-1.1},
  develop:{x:2.0,z:9.8,yaw:-.45}
};
const layouts={
  gallery:canonical,fresh:canonical,
  transfer:[[.15,19.8],[3.55,17.2],[3.95,20.4]],
  develop:[[.5,8.1],[4.2,9.4],[2.4,11.8]]
};
export const layoutNames={gallery:'Castle · 중앙 통로',fresh:'Castle · FRESH-015',transfer:'Castle · 재배치'};
export async function experiment({policy='panel'}={}){
  if(!['current','baseline','peripheral','bin','panel'].includes(policy)) throw Error('Unknown H4 checkpoint');
  for(const name of ['holdout.json','edge-holdout.json','confirmation.json','bin-holdout.json','panel-holdout.json']){
    const response=await fetch(new URL(name,import.meta.url));
    if(!response.ok) throw Error('검증 배치를 읽을 수 없습니다.');
    const suite=await response.json();
    for(const [key,item] of Object.entries(suite.layouts)){
      starts[key]=item.start;
      layouts[key]=item.anchors;
    }
  }
  const sim=await castle(160,120);
  const workerURL=new URL('worker.mjs',import.meta.url);workerURL.searchParams.set('policy',policy);
  const worker=new Worker(workerURL,{type:'module'}),on=new AbortController();
  async function run({layout='gallery',prompt,removed=-1,scoreKey,maxSteps=120},listener=()=>{}){
    if(!Object.hasOwn(layouts,layout))throw Error('Unknown layout');
    sim.place(layouts[layout],removed);const p={...starts[layout]},trace=[];let stop=false,bumped=0,travel=0,firstFrameSHA256;
    if(sim.elevation(p.x,p.z)===null)throw Error('출발점이 NavMesh 밖입니다.');
    await ask(worker,{type:'start',prompt,w:160,h:120},on.signal);
    for(let i=0;i<maxSteps;i++){
      const pixels=sim.render(p).data.buffer;
      if(i===0)firstFrameSHA256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels)),v=>v.toString(16).padStart(2,'0')).join('');
      const o=await ask(worker,{type:'frame',pixels},on.signal,[pixels]);
      trace.push({x:p.x,z:p.z,yaw:p.yaw,a:o.action,logits:o.logits.map(v=>+v.toFixed(4)),score:+o.proposal[0].toFixed(3)});
      listener(sim.ctx.canvas,trace.at(-1),i);
      if(o.action===3){stop=true;break;}
      if(!sim.move(p,o.action))bumped++;else if(o.action===0)travel+=.22;
    }
    sim.render(p);const photo=sim.ctx.canvas.toDataURL('image/png');
    const k=scoreKey??prompts.indexOf(prompt);
    const audit=sim.score(p,k);
    return {policy,layout,anchors:layouts[layout],start:starts[layout],endpoint:{...p},firstFrameSHA256,removed,prompt,scoreKey:k,travel,bumped,steps:trace.length,firstStop:stop,
      success:stop&&audit.success,audit,trace,photo,end:stop?'stop':'step_limit',actions};
  }
  return {run,categories,close(){on.abort();worker.terminate();sim.dispose();}};
}
