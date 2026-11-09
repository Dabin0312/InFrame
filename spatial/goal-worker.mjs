import {goalDetector} from './detector.mjs';
import {goals,VisualStop} from './goals.mjs';
import {Targets} from './geometry.mjs';
let detect,w,h,tracks,stop;
self.onmessage=async({data})=>{
  try{
    if(data.type==='start'){
      w=data.w;h=data.h;detect=await goalDetector(goals[data.goal],w,h);
      tracks=new Targets();stop=new VisualStop();self.postMessage({type:'ready'});return;
    }
    const boxes=await detect(new Uint8Array(data.pixels));
    tracks.update(boxes,null,null,data.t,1);
    const match=stop.step(boxes,w,h,data.t,1);
    self.postMessage({type:'detection',match,boxes});
  }catch(e){self.postMessage({type:'error',message:e.message});}
};
