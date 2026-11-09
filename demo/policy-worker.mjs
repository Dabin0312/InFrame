import * as ort from './vendor/ort.wasm.min.mjs';
import { Controller,reduceRGB } from './controller.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('./vendor/',import.meta.url).href;
let session, controller, history;
self.onmessage=async ({data})=>{
  try{
    if(data.type==='start'){
      const config=await fetch(new URL('policy.json',import.meta.url));
      if(!config.ok)throw Error('모델 설정을 불러오지 못했어요.');
      controller=new Controller(await config.json());history=[];
      session=await ort.InferenceSession.create(new URL('policy.onnx',import.meta.url).href,{executionProviders:['wasm']});
      self.postMessage({type:'ready'});return;
    }
    const image=reduceRGB(new Uint8Array(data.pixels));history.push(image);
    while(history.length<4)history.unshift(image);if(history.length>4)history.shift();
    const seq=new Uint8Array(4*image.length);history.forEach((x,i)=>seq.set(x,i*image.length));
    const input=new ort.Tensor('uint8',seq,[1,4,60,80,3]);
    const out=await session.run({rgb:input});
    const action=controller.step(out.base.data,out.corr.data,out.dock.data,image);
    input.dispose();Object.values(out).forEach(t=>t.dispose());self.postMessage({type:'action',action});
  }catch(err){self.postMessage({type:'error',message:String(err.message||err)});}
};
