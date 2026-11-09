import * as ort from '../demo/vendor/ort.wasm.min.mjs';
import {Controller, reduceRGB} from '../demo/controller.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('../demo/vendor/',import.meta.url).href;
let session, controller, history, memory;

function semanticRGB(buffer){
  const rgba=new Uint8Array(buffer);
  if(rgba.length!==320*240*4)throw Error('Expected a 320 × 240 policy crop.');
  const area=320*320, planar=new Float32Array(3*area).fill(114/255);
  for(let i=0;i<320*240;i++){
    const dst=40*320+i;
    for(let ch=0;ch<3;ch++)planar[ch*area+dst]=rgba[4*i+ch]/255;
  }
  return planar;
}
self.onmessage=async({data})=>{
  try{
    if(data.type==='start'){
      const response=await fetch(new URL('../demo/policy.json',import.meta.url));
      if(!response.ok)throw Error('H4 설정을 읽지 못했습니다.');
      controller=new Controller(await response.json());
      session=await ort.InferenceSession.create(new URL('policy.onnx',import.meta.url).href,{executionProviders:['wasm']});
      history=[];memory=new Float32Array(24).fill(-1);
      self.postMessage({type:'ready'});return;
    }
    const image=reduceRGB(new Uint8Array(data.pixels));history.push(image);
    while(history.length<4)history.unshift(image);
    if(history.length>4)history.shift();
    const seq=new Uint8Array(4*image.length);history.forEach((x,i)=>seq.set(x,i*image.length));
    const inputs={rgb:new ort.Tensor('uint8',seq,[1,4,60,80,3]),
      'semantic/rgb':new ort.Tensor('float32',semanticRGB(data.semantic),[1,3,320,320]),
      'action/memory':new ort.Tensor('float32',memory,[1,3,8])};
    let out;
    try{
      out=await session.run(inputs);memory=out['action/next_memory'].data.slice();
      const base=out.base.data,dock=out.dock.data;
      const baseline=controller.step(base,out.corr.data,dock,image);
      const action=out['action/policy_stop'].data[0]?[0,0,1]:baseline;
      const raw={baseStop:base[3],distance:Math.expm1(Math.min(4,Math.max(0,base[2]))),
        near:dock[0],ready:dock[1],learnedLogit:out['action/stop_logit'].data[0],
        proposal:Array.from(out['action/observation'].data)};
      self.postMessage({type:'action',baseline,action,raw});
    }finally{Object.values(inputs).forEach(t=>t.dispose());if(out)Object.values(out).forEach(t=>t.dispose());}
  }catch(e){self.postMessage({type:'error',message:String(e.message||e)});}
};
