import {AlvaAR} from './alva.mjs';
import jsfeat from './features.mjs';
import * as ort from '../demo/vendor/ort.wasm.min.mjs';
import {ray,triangulate,Targets} from './geometry.mjs';
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('../demo/vendor/',import.meta.url).href;
let slam,detector,w,h,prev,curr,tracks=[],seg=1,cloud=[],grid=new Set(),targets=new Targets();
function pyramid(){const p=new jsfeat.pyramid_t(3);p.allocate(w,h,jsfeat.U8_t|jsfeat.C1_t);return p;}
function landmarks(image,pose){
  jsfeat.imgproc.grayscale(image,w,h,curr.data[0]);curr.build(curr.data[0],true);
  if(!pose){tracks=[];[prev,curr]=[curr,prev];return;}
  const rays=(x,y)=>ray(pose,x,y,slam.intrinsics);
  if(tracks.length){
    const n=tracks.length,a=new Float32Array(n*2),b=new Float32Array(n*2),ok=new Uint8Array(n);
    tracks.forEach((tr,i)=>{a[2*i]=tr.x;a[2*i+1]=tr.y;});
    jsfeat.optical_flow_lk.track(prev,curr,a,b,n,17,20,ok,.01,.001);
    tracks=tracks.filter((tr,i)=>{
      const x=b[2*i],y=b[2*i+1];if(!ok[i]||x<9||x>w-9||y<9||y>h-9)return false;
      tr.x=x;tr.y=y;tr.age++;
      if(tr.age%3===0)tr.rays.push(rays(x,y));
      if(tr.rays.length>=3){
        const p=triangulate(tr.rays,.009);
        if(p){
          const key=[seg,...p.map(v=>Math.round(v*48))].join('/');
          if(!grid.has(key)&&cloud.length<6000){cloud.push({p,seg});grid.add(key);}
          return false;
        }
      }
      return tr.age<55;
    });
  }
  if(tracks.length<48){
    // FAST only writes to detected entries, preallocate reusable keypoints.
    const c=keypoints;
    const n=jsfeat.fast_corners.detect(curr.data[0],c,12);
    const ranked=c.slice(0,n).sort((a,b)=>b.score-a.score);
    for(const {x,y} of ranked){
      if(!tracks.some(tr=>(tr.x-x)**2+(tr.y-y)**2<180))tracks.push({x,y,rays:[rays(x,y)],age:0});
      if(tracks.length>=90)break;
    }
  }
  [prev,curr]=[curr,prev];
}
let keypoints,canvas,ctx,localized=false;
async function detect(image){
  const size=320,scale=Math.min(size/w,size/h),dw=Math.round(w*scale),dh=Math.round(h*scale);
  const dx=Math.floor((size-dw)/2),dy=Math.floor((size-dh)/2);
  const data=new Float32Array(3*size*size).fill(114/255);
  ctx.putImageData(new ImageData(new Uint8ClampedArray(image.buffer),w,h),0,0);
  const small=new OffscreenCanvas(dw,dh),g=small.getContext('2d',{willReadFrequently:true});
  g.drawImage(canvas,0,0,dw,dh);const rgba=g.getImageData(0,0,dw,dh).data;
  for(let y=0;y<dh;y++)for(let x=0;x<dw;x++){
    const i=4*(y*dw+x),j=(dy+y)*size+dx+x;
    for(let c=0;c<3;c++)data[j+c*size*size]=rgba[i+c]/255;
  }
  const tensor=new ort.Tensor('float32',data,[1,3,size,size]);
  const out=await detector.run({rgb:tensor}),v=out.boxes.data,n=v.length/5,choices=[];
  for(let i=0;i<n;i++){
    if(v[4*n+i]<.30)continue;
    const bw=v[2*n+i]/scale,bh=v[3*n+i]/scale,x=(v[i]-dx)/scale-bw/2,y=(v[n+i]-dy)/scale-bh/2;
    const left=Math.max(0,x),top=Math.max(0,y),right=Math.min(w,x+bw),bottom=Math.min(h,y+bh);
    if(right-left>=4&&bottom-top>=6)choices.push({box:[left,top,right-left,bottom-top],score:v[4*n+i]});
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
self.onmessage=async({data})=>{
  try{
    if(data.type==='start'){
      w=data.w;h=data.h;
      slam=await AlvaAR.Initialize(w,h,data.fov/Math.max(1,w/h));
      detector=await ort.InferenceSession.create(new URL('extinguisher.onnx',import.meta.url).href,{executionProviders:['wasm']});
      prev=pyramid();curr=pyramid();keypoints=Array.from({length:w*h},()=>new jsfeat.keypoint_t());
      canvas=new OffscreenCanvas(w,h);ctx=canvas.getContext('2d',{willReadFrequently:true});
      self.postMessage({type:'ready',k:slam.intrinsics});return;
    }
    const image=new Uint8Array(data.pixels),start=cloud.length;
    // AlvaAR reads the system clock. Recorded video requires timestamps from its own timeline.
    const wallClock=Date.now;let state;
    try{Date.now=()=>1600000000000+Math.round(data.t*1000);slam.memImg.write(image);state=slam.system.findCameraPose(slam.memImg.ptr,slam.memCam.ptr);}
    finally{Date.now=wallClock;}
    if(state===2){if(localized)seg++;localized=false;tracks=[];}
    if(state===1)localized=true;
    const pose=state===1?Array.from(slam.memCam.read(16)):null;
    landmarks(image,pose);
    const boxes=data.detect?await detect(image):[];
    if(data.detect)targets.update(boxes,pose,slam.intrinsics,data.t,seg);
    self.postMessage({type:'mapped',state,seg,pose,points:cloud.slice(start),boxes,targets:data.detect?targets.tracks.filter(x=>x.p).map(x=>({id:x.id,seg:x.seg,p:x.p,t:x.times[0],last:x.last,n:x.times.length})):undefined});
  }catch(e){self.postMessage({type:'error',message:String(e.stack||e)});}
};
