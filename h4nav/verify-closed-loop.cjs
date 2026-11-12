// Independent replay audit: re-render the recorded poses and recompute each input
// hash, final photo, target ID mask and STOP score without loading the policy.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require('playwright-core');
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
function assert(value,message){if(!value)throw Error(message);}
async function inspect(sim,{r,limit}){
  const cache=new Map();
  sim.place(r.anchors,r.removed);
  function valid(ok,msg){if(!ok)throw Error(r.id+' '+msg);}
  async function frameHash(p){
    const key=[p.x,p.z,p.yaw].join(',');
    if(cache.has(key))return cache.get(key);
    const bytes=sim.render(p).data,rgb=new Uint8Array(160*120*3);
    for(let j=0,i=0;j<bytes.length;j+=4,i+=3){rgb[i]=bytes[j];rgb[i+1]=bytes[j+1];rgb[i+2]=bytes[j+2];}
    const h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',rgb)),b=>b.toString(16).padStart(2,'0')).join('');
    cache.set(key,h);
    return h;
  }
  let previous=r.start,travel=0,advances=0,changedAfterAdvance=0,stops=0,turns=0,blocked=0;
  for(let i=0;i<r.steps.length;i++){
    const s=r.steps[i],p=s.before,q=s.after,cmd=s.sent;
    valid(['x','z','yaw'].every(k=>p[k]===previous[k]),'pose discontinuity');
    valid(await frameHash(p)===s.rgb,'RGB hash mismatch at '+s.i);
    const next=[[.4,0,0],[0,0,1],[0,0,-1],[0,0,0]][s.action];
    valid(cmd.every((v,k)=>v===next[k]),'unexpected emitted twist');
    valid(Math.abs((q.yaw-p.yaw)-cmd[2]*.25)<1e-10,'yaw does not track command');
    const dx=q.x-p.x,dz=q.z-p.z,d=Math.hypot(dx,dz);
    valid(Math.abs(d-s.distance)<1e-9&&d<=cmd[0]*.25+1e-9,'velocity integration mismatch');
    if(cmd[0] && !s.blocked)valid(Math.abs(d-.10)<1e-9,'uncapped forward step');
    if(d>0)valid(Math.abs(dx+d*Math.sin(p.yaw))<1e-9&&Math.abs(dz+d*Math.cos(p.yaw))<1e-9,'forward axis mismatch');
    travel+=d;blocked+=Number(s.blocked);
    if(d>0){advances++;changedAfterAdvance+=Number(await frameHash(q)!==s.rgb);}
    if(cmd[2])turns++;
    if(s.action===3){stops++;valid(i===r.steps.length-1,'action after STOP');}
    previous=q;
  }
  valid(stops===Number(r.stopped)&&Math.abs(travel-r.traveled)<1e-8&&r.blocked===blocked,'episode totals');
  valid(r.stopped||r.steps.length===limit,'early termination');
  valid(r.stopStep===(r.stopped?r.steps.length:null),'first STOP does not match');
  valid(['x','z','yaw'].every(k=>r.endpoint[k]===previous[k]),'incorrect endpoint');
  valid(r.minCenterClearance>=r.footRadius,'footprint outside permitted floor');
  sim.render(previous);
  valid(sim.ctx.canvas.toDataURL('image/png')===r.photo,'terminal photograph mismatch');
  const {pixels,box}=sim.labels(previous)[r.goal],a=r.anchors[r.goal];
  const distance=Math.hypot(previous.x-a[0],previous.z-a[1]);
  const centered=pixels>0&&Math.abs((box[0]+box[2])/320-.5)<=.25;
  const eligible=pixels>=80&&centered&&distance<=1.35;
  valid(pixels===r.audit.visiblePixels,'terminal ID mask mismatch');
  if(r.removed===r.goal)valid(pixels===0&&r.audit.distance===null,'removed target remains');
  else valid(Math.abs(distance-r.audit.distance)<1e-9&&eligible===r.audit.success,'goal score mismatch');
  const end=!r.stopped?'step_limit':r.removed===r.goal?'false_stop':eligible?'success':'invalid_stop';
  valid(end===r.end,'misclassified result');
  return {id:r.id,frames:r.steps.length,distinctPoses:cache.size,advances,changedAfterAdvance,turns,blocked,photoVerified:true};
}
async function main(){
  const [base,suitePath,out]=process.argv.slice(2),suiteBytes=fs.readFileSync(suitePath),suite=JSON.parse(suiteBytes);
  const uri=base.replace(/\/?$/,'/'),browser=await chromium.launch({channel:'chrome',args:process.platform==='darwin'?['--use-angle=metal']:[]});
  const results=[];
  try{
    const page=await browser.newPage();await page.goto(uri+'spatial/floor.json');
    const sim=await page.evaluateHandle(async url=>(await import(url)).castle(160,120),uri+'h4nav/castle.mjs');
    // Playwright serializes the function and its argument; the policy is never imported here.
    for(const layout of suite.layouts){
      const common=new Set();
      for(let goal=0;goal<3;goal++)for(const removed of [-1,goal]){
        const id=layout.id+'-'+goal+(removed===-1?'-present':'-absent');
        const r=JSON.parse(fs.readFileSync(path.join(out,id+'.json')));
        assert(r.id===id&&r.goal===goal&&r.removed===removed&&r.suiteHash===digest(suiteBytes)&&
          r.policySHA256===suite.policySHA256&&r.prompt===suite.goals[goal]&&
          JSON.stringify(r.start)===JSON.stringify(layout.start)&&JSON.stringify(r.anchors)===JSON.stringify(layout.anchors),'Frozen input mismatch '+id);
        if(removed===-1)common.add(r.steps[0].rgb);
        results.push(await sim.evaluate(inspect,{r,limit:suite.stepLimit}));
      }
      assert(common.size===1,'Initial RGB differs across goals '+layout.id);
      console.log(layout.id,'6 cases verified');
    }
    await sim.evaluate(s=>s.dispose());
    fs.writeFileSync(path.join(out,'audit.json'),JSON.stringify({suiteHash:digest(suiteBytes),cases:results},null,2));
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
