export function waitEvent(el,name,signal,action){
  return new Promise((resolve,reject)=>{
    const finish=(err)=>{clearTimeout(timer);el.removeEventListener(name,done);el.removeEventListener('error',error);signal.removeEventListener('abort',abort);err?reject(err):resolve();};
    const done=()=>finish(),error=()=>finish(Error('영상을 읽을 수 없습니다. H.264 MP4로 다시 선택해 주세요.')),abort=()=>finish(new DOMException('취소','AbortError'));
    const timer=setTimeout(()=>finish(Error('영상 읽기 시간이 초과되었습니다. H.264 MP4로 다시 시도해 주세요.')),30000);
    el.addEventListener(name,done,{once:true});el.addEventListener('error',error,{once:true});signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted)return abort();try{action();}catch(e){finish(e);}
  });
}
export function ask(worker,msg,signal,transfer=[]){
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
