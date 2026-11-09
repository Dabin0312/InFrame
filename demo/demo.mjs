const $=s=>document.querySelector(s);
const shown=$('#clip'),file=$('#file'),status=$('#status');
const canvas=document.createElement('canvas');canvas.width=192;canvas.height=144;
const ctx=canvas.getContext('2d',{willReadFrequently:true});
let active=null, results=[],sourceName='',sourceUrl='';
function waitEvent(el,name,signal,action){
  return new Promise((resolve,reject)=>{
    const finish=(err)=>{clearTimeout(timer);el.removeEventListener(name,done);el.removeEventListener('error',error);signal.removeEventListener('abort',abort);err?reject(err):resolve();};
    const done=()=>finish(),error=()=>finish(Error('영상을 읽을 수 없습니다. H.264 MP4로 다시 선택해 주세요.')),abort=()=>finish(new DOMException('취소','AbortError'));
    const timer=setTimeout(()=>finish(Error('영상 읽기 시간이 초과되었습니다. H.264 MP4로 다시 시도해 주세요.')),30000);
    el.addEventListener(name,done,{once:true});el.addEventListener('error',error,{once:true});signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted)return abort();try{action();}catch(e){finish(e);}
  });
}
function ask(worker,msg,signal,transfer=[]){
  return new Promise((resolve,reject)=>{
    function end(err,value){clearTimeout(timer);worker.removeEventListener('message',response);worker.removeEventListener('error',error);signal.removeEventListener('abort',abort);if(err)reject(err);else resolve(value);}
    const response=e=>e.data.type==='error'?end(Error(e.data.message)):end(null,e.data);
    const error=()=>end(Error('모델을 불러올 수 없습니다. 최신 브라우저에서 다시 시도해 주세요.'));
    const abort=()=>end(new DOMException('취소','AbortError'));
    const timer=setTimeout(()=>end(Error('모델 응답 시간이 초과되었습니다. 다시 시도해 주세요.')),90000);
    worker.addEventListener('message',response);worker.addEventListener('error',error);signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted)return abort();worker.postMessage(msg,transfer);
  });
}
function stop(){if(active){active.abort();active=null;}}
function show(r){
  $('#at').textContent=r.t.toFixed(2)+' s';$('#forward').textContent=r.forward.toFixed(3)+' m/s';$('#yaw').textContent=r.yaw.toFixed(3)+' rad/s';
  $('#decision').textContent=r.stop?'정지':r.forward>.001?'전진':r.yaw>0?'좌회전':r.yaw<0?'우회전':'대기';
}
function output(label){
  $('#summary').textContent=label;$('#download').hidden=!results.length;$('#review').hidden=!results.length;
  $('#tick').max=Math.max(0,results.length-1);$('#tick').value=Math.max(0,results.length-1);
}
async function start(blob,name){
  stop();
  const controller=new AbortController(),signal=controller.signal;active=controller;
  if(sourceUrl)URL.revokeObjectURL(sourceUrl);sourceUrl=blob?URL.createObjectURL(blob):'';
  sourceName=name;results=[];output('');$('#session').hidden=false;$('#source-name').textContent=name;$('#cancel').hidden=false;
  $('#decision').textContent='준비 중';['#at','#forward','#yaw'].forEach(k=>$(k).textContent='—');
  status.textContent='영상 읽는 중…';let worker;
  try{
    await waitEvent(shown,'loadeddata',signal,()=>{shown.src=sourceUrl||'sample.mp4';shown.load();});
    if(!Number.isFinite(shown.duration)||shown.duration<=0||!shown.videoWidth)throw Error('길이를 읽을 수 있는 MP4 또는 WebM을 선택해 주세요.');
    status.textContent='기기에서 정책을 준비하고 있어요…';
    worker=new Worker(new URL('policy-worker.mjs',import.meta.url),{type:'module'});await ask(worker,{type:'start'},signal);
    const w=shown.videoWidth,h=shown.videoHeight,sw=Math.min(w,h*4/3),sh=sw*3/4;
    let atlas;
    if(!blob){atlas=new Image();atlas.src='sample-rgb.png';await atlas.decode();if(signal.aborted)throw new DOMException('취소','AbortError');}
    const count=atlas?70:Math.ceil(shown.duration*4-1e-6);
    for(let i=0;i<count;i++){
      const t=i/4;if(t>0)await waitEvent(shown,'seeked',signal,()=>{shown.currentTime=t;});
      if(atlas)ctx.drawImage(atlas,(i%10)*192,Math.floor(i/10)*144,192,144,0,0,192,144);
      else ctx.drawImage(shown,(w-sw)/2,(h-sh)/2,sw,sh,0,0,192,144);
      const pixels=ctx.getImageData(0,0,192,144).data.buffer;
      const {action}=await ask(worker,{type:'frame',pixels},signal,[pixels]);
      const r={t,forward:action[0],yaw:action[1],stop:Boolean(action[2])};results.push(r);show(r);
      if(i%4===0)status.textContent='분석 중 · '+(i+1)+' / '+count+' 프레임';
      if(r.stop)break;
    }
    status.textContent='분석 완료';output(results.length+'개 관측 · '+(results.at(-1)?.stop?'첫 STOP '+results.at(-1).t.toFixed(2)+' s':'영상 끝까지 STOP 없음'));
  }catch(e){
    if(active!==controller)return;
    if(signal.aborted){status.textContent='분석을 취소했어요.';}else{status.textContent=e.message;}
    output('');
  }finally{worker?.terminate();if(active===controller){$('#cancel').hidden=true;active=null;}}
}
file.onchange=()=>{const f=file.files[0];file.value='';if(f)start(f,f.name);};
$('#sample').onclick=()=>start(null,'FRESH–015 · 샘플 주행');$('#cancel').onclick=()=>active?.abort();
$('#tick').oninput=()=>{const r=results[Number($('#tick').value)];if(r){shown.currentTime=r.t;show(r);}};
$('#download').onclick=()=>{const blob=new Blob([JSON.stringify({source:sourceName,goal:'소화기',mode:'recorded_rgb',hz:4,units:{t:'s',forward:'m/s',yaw:'rad/s'},frames:results},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='inframe-actions.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
const drop=$('#drop');['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over');}));drop.ondragleave=()=>drop.classList.remove('over');drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');const f=e.dataTransfer.files[0];if(f)start(f,f.name);};
