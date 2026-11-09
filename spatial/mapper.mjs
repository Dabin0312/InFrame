import {AlvaAR} from './alva.mjs';
import jsfeat from './features.mjs';
import {ray,triangulate,Targets} from './geometry.mjs';
import {goalDetector} from './detector.mjs';
import {maskView,confirmedAnchor} from './mask-map.mjs';
import {goals} from './goals.mjs';
let slam,detect,w,h,prev,curr,tracks=[],seg=1,cloud=[],grid=new Set(),targets=new Targets();
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
let keypoints,localized=false;
self.onmessage=async({data})=>{
  try{
    if(data.type==='start'){
      w=data.w;h=data.h;
      slam=await AlvaAR.Initialize(w,h,data.fov/Math.max(1,w/h));
      detect=data.goal==='custom'
        ?await (await import('./open-detector.mjs')).openDetector(data.prompt,w,h)
        :await goalDetector(goals[data.goal??'extinguisher'],w,h);
      prev=pyramid();curr=pyramid();keypoints=Array.from({length:w*h},()=>new jsfeat.keypoint_t());
      self.postMessage({type:'ready',k:slam.intrinsics});return;
    }
    const image=new Uint8Array(data.pixels),start=cloud.length;
    // AlvaAR reads the system clock. Recorded video requires timestamps from its own timeline.
    const wallClock=Date.now;let state;
    try{Date.now=()=>1600000000000+Math.round(data.t*1000);slam.memImg.write(image);state=slam.system.findCameraPose(slam.memImg.ptr,slam.memCam.ptr);}
    finally{Date.now=wallClock;}
    if(data.type==='warmup'){self.postMessage({type:'warmed'});return;}
    if(state===2){if(localized)seg++;localized=false;tracks=[];}
    if(state===1)localized=true;
    const pose=state===1?Array.from(slam.memCam.read(16)):null;
    landmarks(image,pose);
    const boxes=data.detect?await detect(image):[];
    if(data.detect){
      targets.update(boxes,pose,slam.intrinsics,data.t,seg);
      for(const b of boxes){
        if(!b.mask)continue;
        const tr=targets.tracks.find(tr=>tr.id===b.track);
        tr.views??=[];
        if(pose){
          tr.views.push(maskView(pose,slam.intrinsics,b,data.t));
          if(tr.views.length>12)tr.views.splice(1,1);
          tr.anchor=confirmedAnchor(tr.views);
          // Bridge a detection gap only when one earlier track in this submap
          // supports the same 3D point, including the newest held-out mask.
          if(!tr.anchor&&tr.views.length>=2){
            const eligible=targets.tracks.filter(a=>a!==tr&&a.seg===tr.seg&&a.views?.length>=2&&
              !a.merged&&a.last<tr.times[0]-.25&&tr.times[0]-a.last<=8);
            const links=eligible.map(a=>({a,p:confirmedAnchor([...a.views,...tr.views])})).filter(l=>l.p);
            if(links.length===1){
              const {a,p}=links[0];tr.anchor=p;tr.views=[...a.views,...tr.views].slice(-12);
              tr.alias=a.alias??a.id;a.merged=true;a.p=null;
            }
          }
          if(tr.anchor)tr.evidence=data.t;
        }
        tr.p=tr.anchor??null;
        b.track=tr.alias??tr.id;delete b.mask;
      }
    }
    self.postMessage({type:'mapped',state,seg,pose,points:cloud.slice(start),boxes,targets:data.detect?targets.tracks.filter(x=>x.p&&!x.merged).map(x=>({id:x.alias??x.id,seg:x.seg,p:x.p,t:x.evidence??x.times[0],last:x.last,n:x.views?.length??x.times.length})):undefined});
  }catch(e){self.postMessage({type:'error',message:String(e.stack||e)});}
};
