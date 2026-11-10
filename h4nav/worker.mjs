// The runtime boundary is intentionally narrow: one text prompt, then front RGB.
import * as ort from '../demo/vendor/ort.wasm.min.mjs';
import {openDetector} from '../spatial/open-detector.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('../demo/vendor/',import.meta.url).href;
let detector,student,embedding,history=[],channels,w,h,ctx,small;
let previousAction=-1,memory=new Float32Array(40);
async function init(prompt,width,height){
  w=width;h=height;history=[];previousAction=-1;memory.fill(0);channels=new Map();
  if(detector)await detector.release();embedding?.dispose();
  detector=await openDetector(prompt,w,h);
  embedding=new ort.Tensor('float32',detector.embedding,[1,512]);
  const checkpoints={baseline:'baseline.onnx',current:'student.onnx',peripheral:'peripheral.onnx',bin:'bin-h4.onnx'};
  const id=new URL(self.location.href).searchParams.get('policy')??'bin';
  student??=await ort.InferenceSession.create(new URL(checkpoints[id],import.meta.url).href,{executionProviders:['wasm']});
  memory=new Float32Array(['bin','peripheral'].includes(id)?44:40);
  ctx=new OffscreenCanvas(w,h).getContext('2d');small=new OffscreenCanvas(80,60).getContext('2d',{willReadFrequently:true});
}
function key(data){let k=2166136261;for(const byte of data)k=Math.imul(k^byte,16777619);return k>>>0;}
async function act(pixels){
  const hash=key(pixels);let f=channels.get(hash);
  if(!f||!pixels.every((v,i)=>v===f.source[i])){
    const box=(await detector(pixels))[0],proposal=new Float32Array(5);
    if(box){const [x,y,bw,bh]=box.box;proposal.set([box.score,(x+bw/2)/w,(y+bh/2)/h,bw/w,bh/h]);}
    ctx.putImageData(new ImageData(new Uint8ClampedArray(pixels.buffer),w,h),0,0);
    small.drawImage(ctx.canvas,0,0,80,60);const bytes=small.getImageData(0,0,80,60).data,rgb=new Uint8Array(80*60*3);
    for(let i=0;i<4800;i++)rgb.set(bytes.subarray(4*i,4*i+3),3*i);
    f={rgb,proposal,source:pixels};if(channels.size>=64)channels.delete(channels.keys().next().value);channels.set(hash,f);
  }
  history.push(f);while(history.length<4)history.unshift(f);if(history.length>4)history.shift();
  const seq=new Uint8Array(4*14400),proposals=new Float32Array(20);
  history.forEach((o,i)=>{seq.set(o.rgb,14400*i);proposals.set(o.proposal,5*i);});
  const rgb=new ort.Tensor('uint8',seq,[1,4,60,80,3]),obs=new ort.Tensor('float32',proposals,[1,4,5]);
  const inputs={rgb,goal_embedding:embedding,rgb_goal_proposals:obs};
  if(student.inputNames.includes('camera')){
    const camera=new Uint8Array(w*h*3);
    for(let i=0;i<w*h;i++){
      camera[3*i]=pixels[4*i];camera[3*i+1]=pixels[4*i+1];camera[3*i+2]=pixels[4*i+2];
    }
    inputs.camera=new ort.Tensor('uint8',camera,[1,h,w,3]);
  }
  if(student.inputNames.includes('memory')){
    const last=new Float32Array(4);last[previousAction+1]=1;
    inputs.previous_action=new ort.Tensor('float32',last,[1,4]);
    inputs.memory=new ort.Tensor('float32',memory,[1,1,memory.length]);
  }
  try{
    const {action_logits,next_memory}=await student.run(inputs);
    if(next_memory){memory=Float32Array.from(next_memory.data);next_memory.dispose();}
    const logits=Array.from(action_logits.data);action_logits.dispose();
    if(!logits.every(Number.isFinite))throw Error('정책의 행동 점수를 읽을 수 없습니다.');
    previousAction=logits.indexOf(Math.max(...logits));
    return {action:previousAction,logits,proposal:Array.from(f.proposal)};
  }finally{rgb.dispose();obs.dispose();inputs.previous_action?.dispose();inputs.memory?.dispose();inputs.camera?.dispose();}
}
self.onmessage=async({data})=>{
  try{
    if(data.type==='start'){await init(data.prompt,data.w,data.h);self.postMessage({type:'ready'});}
    else if(data.type==='frame'){self.postMessage({type:'result',...await act(new Uint8Array(data.pixels))});}
    else throw Error('지원하지 않는 정책 입력입니다.');
  }catch(e){self.postMessage({type:'error',message:String(e.message||e)});}
};
