import * as ort from '../demo/vendor/ort.wasm.min.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('../demo/vendor/',import.meta.url).href;
export async function goalDetector(goal,w,h){
  const detector=await ort.InferenceSession.create(new URL(goal.asset,import.meta.url).href,{executionProviders:['wasm']});
  const canvas=new OffscreenCanvas(w,h),ctx=canvas.getContext('2d',{willReadFrequently:true});
  async function detect(image){
    const size=320,scale=Math.min(size/w,size/h),dw=Math.round(w*scale),dh=Math.round(h*scale);
    const dx=Math.floor((size-dw)/2),dy=Math.floor((size-dh)/2);
    const data=new Float32Array(3*size*size).fill(114/255);
    ctx.putImageData(new ImageData(new Uint8ClampedArray(image.buffer,image.byteOffset,image.byteLength),w,h),0,0);
    const small=new OffscreenCanvas(dw,dh),g=small.getContext('2d',{willReadFrequently:true});
    g.drawImage(canvas,0,0,dw,dh);const rgba=g.getImageData(0,0,dw,dh).data;
    for(let y=0;y<dh;y++)for(let x=0;x<dw;x++){
      const i=4*(y*dw+x),j=(dy+y)*size+dx+x;
      for(let c=0;c<3;c++)data[j+c*size*size]=rgba[i+c]/255;
    }
    const tensor=new ort.Tensor('float32',data,[1,3,size,size]);
    const out=await detector.run({rgb:tensor}),v=out.boxes.data,n=out.boxes.dims[2],ch=4+goal.channel,choices=[];
    for(let i=0;i<n;i++){
      if(v[ch*n+i]<.30)continue;
      const bw=v[2*n+i]/scale,bh=v[3*n+i]/scale,x=(v[i]-dx)/scale-bw/2,y=(v[n+i]-dy)/scale-bh/2;
      const left=Math.max(0,x),top=Math.max(0,y),right=Math.min(w,x+bw),bottom=Math.min(h,y+bh);
      if(right-left>=4&&bottom-top>=6)choices.push({box:[left,top,right-left,bottom-top],score:v[ch*n+i]});
    }
    tensor.dispose();out.boxes.dispose();
    const selected=[];
    for(const o of choices.sort((a,b)=>b.score-a.score)){
      if(selected.some(p=>{
        const [a,b,c,d]=p.box,[x,y,w,h]=o.box;
        const overlap=Math.max(0,Math.min(a+c,x+w)-Math.max(a,x))*Math.max(0,Math.min(b+d,y+h)-Math.max(b,y));
        return overlap/(c*d+w*h-overlap)>.45;
      }))continue;
      selected.push(o);if(selected.length>=10)break;
    }
    return selected;
  }
  return detect;
}
