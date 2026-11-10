import * as ort from '../demo/vendor/ort.wasm.min.mjs';
import {tokenizer} from './prompt.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('../demo/vendor/',import.meta.url).href;
async function asset(path){
  const response=await fetch(new URL(path,import.meta.url));
  if(!response.ok)throw Error('모델 파일을 읽을 수 없어요 ('+response.status+'). 새로고침 후 다시 시도하세요.');
  return response;
}
export async function openDetector(prompt,w,h){
  const opt={executionProviders:['wasm']},size=416;
  const manifest=await (await asset('prompt-model.json')).json();
  const [pieces,merges]=await Promise.all([Promise.all(manifest.text.map(async path=>new Uint8Array(await (await asset(path)).arrayBuffer()))),(await asset('prompt-merges.txt')).text()]);
  const bytes=new Uint8Array(manifest.size);let offset=0;
  for(const piece of pieces){bytes.set(piece,offset);offset+=piece.length;}
  if(offset!==bytes.length)throw Error('텍스트 모델 다운로드가 중단됐어요.');
  const encoder=await ort.InferenceSession.create(bytes,opt);
  const tokens=new ort.Tensor('int32',tokenizer(merges)(prompt),[1,77]);
  let emb;
  try{emb=(await encoder.run({tokens})).embedding;}finally{tokens.dispose();await encoder.release();}
  const net=await ort.InferenceSession.create(new URL(manifest.vision,import.meta.url).href,opt);
  const scale=Math.min(size/w,size/h),dw=Math.round(w*scale),dh=Math.round(h*scale),dx=Math.floor((size-dw)/2),dy=Math.floor((size-dh)/2);
  const input=new OffscreenCanvas(w,h).getContext('2d'),ctx=new OffscreenCanvas(size,size).getContext('2d',{willReadFrequently:true});
  const detect=async pixels=>{
    input.putImageData(new ImageData(new Uint8ClampedArray(pixels.buffer,pixels.byteOffset,pixels.byteLength),w,h),0,0);
    ctx.fillStyle='rgb(114,114,114)';ctx.fillRect(0,0,size,size);ctx.drawImage(input.canvas,dx,dy,dw,dh);
    const rgba=ctx.getImageData(0,0,size,size).data,area=size*size,chs=new Float32Array(3*area);
    for(let i=0;i<area;i++){chs[i]=rgba[i*4]/255;chs[i+area]=rgba[i*4+1]/255;chs[i+area*2]=rgba[i*4+2]/255;}
    const rgb=new ort.Tensor('float32',chs,[1,3,size,size]);
    const {boxes,proto}=await net.run({rgb,embedding:emb});rgb.dispose();
    const [,channels,n]=boxes.dims,v=boxes.data,choices=[];
    for(let i=0;i<n;i++){
      const score=v[4*n+i];if(!Number.isFinite(score)||score<.25)continue;
      const left=Math.max(0,(v[i]-v[2*n+i]/2-dx)/scale),right=Math.min(w,(v[i]+v[2*n+i]/2-dx)/scale);
      const top=Math.max(0,(v[n+i]-v[3*n+i]/2-dy)/scale),bottom=Math.min(h,(v[n+i]+v[3*n+i]/2-dy)/scale);
      if(right-left>=5&&bottom-top>=6)choices.push({i,score,box:[left,top,right-left,bottom-top]});
    }
    const out=[],grid=24,[,,ph,pw]=proto.dims,basis=proto.data;
    for(const {i,score,box} of choices.sort((a,b)=>b.score-a.score)){
      const [x,y,bw,bh]=box;
      if(out.some(({box:[a,b,c,d]})=>{const k=Math.max(0,Math.min(a+c,x+bw)-Math.max(a,x))*Math.max(0,Math.min(b+d,y+bh)-Math.max(b,y));return k/(c*d+bw*bh-k)>.45;}))continue;
      const mask=new Uint8Array(grid*grid);
      for(let r=0;r<grid;r++)for(let c=0;c<grid;c++){
        const u=Math.min(pw-1,Math.floor(((x+(c+.5)*bw/grid)*scale+dx)*pw/size));
        const t=Math.min(ph-1,Math.floor(((y+(r+.5)*bh/grid)*scale+dy)*ph/size));
        let logit=0;for(let a=5;a<channels;a++)logit+=v[a*n+i]*basis[(a-5)*ph*pw+t*pw+u];
        mask[r*grid+c]=Number(logit>0);
      }
      out.push({score,box,mask});if(out.length===10)break;
    }
    boxes.dispose();proto.dispose();return out;
  };
  detect.embedding=Float32Array.from(emb.data);
  detect.release=async()=>{emb.dispose();await net.release();};
  return detect;
}
