// Usage: node h4nav/go2-closed-loop.cjs preflight|run BASE_URL SUITE RESULT_DIR [SHARD SHARDS]
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function policyProcess(){
  const child=spawn(process.env.PYTHON||'python3',[path.join(__dirname,'closed-loop-policy.py')],{stdio:['pipe','pipe','inherit']});
  const lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator]();
  return {async request(msg){
    child.stdin.write(JSON.stringify(msg)+'\n');
    const r=await lines.next();
    if(r.done)throw Error('H4 inference process exited');
    return JSON.parse(r.value);
  },close(){child.stdin.end();child.kill();}};
}
async function main(){
  const [mode,base,suitePath,out,shard='0',shards='1']=process.argv.slice(2);
  if(!['preflight','run'].includes(mode)||!suitePath)throw Error('Expected preflight|run BASE_URL SUITE RESULT_DIR [SHARD SHARDS]');
  const rank=Number(shard),count=Number(shards);
  if(mode==='run'&&(!out||!Number.isInteger(count)||count<1||!Number.isInteger(rank)||rank<0||rank>=count))throw Error('Invalid output directory or shard');
  const baseURL=base.replace(/\/?$/,'/');
  const browser=await chromium.launch({channel:'chrome',args:process.platform==='darwin'?['--use-angle=metal']:[]});
  let policy;
  try{
    const page=await browser.newPage();
    await page.goto(baseURL+'spatial/floor.json');
    if(mode==='preflight'){
      const suite=await page.evaluate(async url=>(await import(url)).makeSuite(),baseURL+'h4nav/closed-loop-layouts.mjs');
      fs.writeFileSync(suitePath,JSON.stringify(suite,null,2)+'\n',{flag:'wx'});
      console.log('Frozen holdout:',hash(fs.readFileSync(suitePath)),suite.layouts.length);return;
    }
    const bytes=fs.readFileSync(suitePath),suite=JSON.parse(bytes),suiteHash=hash(bytes);
    if(hash(fs.readFileSync(path.join(__dirname,'transfer-h4.onnx')))!==suite.policySHA256)throw Error('Checkpoint changed');
    fs.mkdirSync(out,{recursive:true});
    policy=policyProcess();
    await page.exposeFunction('decide',png=>policy.request({type:'frame',png}));
    const world=await page.evaluateHandle(async url=>(await import(url)).setup(),baseURL+'h4nav/closed-loop-world.mjs');
    for(let index=rank;index<suite.layouts.length;index+=count){
      const layout=suite.layouts[index];
      for(let goal=0;goal<3;goal++)for(const removed of [-1,goal]){
        const key=layout.id+'-'+goal+(removed===-1?'-present':'-absent'),file=path.join(out,key+'.json');
        if(fs.existsSync(file)){
          const saved=JSON.parse(fs.readFileSync(file));
          if(saved.suiteHash===suiteHash&&saved.policySHA256===suite.policySHA256&&saved.id===key)continue;
          throw Error('Old result does not belong to this suite: '+key);
        }
        await policy.request({type:'start',goal:suite.goals[goal]});
        const r=await world.evaluate((world,options)=>world.run(options),{layout,goal,removed,limit:suite.stepLimit});
        const terminal=await policy.request({type:'end'});
        if(terminal.stopReason!==(r.stopped?'goal_stop':'step_limit'))throw Error('Stop reason mismatch');
        Object.assign(r,{id:key,suiteHash,policySHA256:suite.policySHA256,terminal});
        fs.writeFileSync(file+'.tmp',JSON.stringify(r));fs.renameSync(file+'.tmp',file);
        console.log(key,r.end,r.steps.length,r.blocked,new Date().toISOString());
      }
    }
    await world.evaluate(world=>world.sim.dispose());
  }finally{policy?.close();await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
