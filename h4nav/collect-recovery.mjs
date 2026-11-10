// Privileged demonstrations for learning how to move again. Used only at training time.
import {castle} from './castle.mjs';

export async function collectRecovery(emit,{count=640,seed=303819}={}){
  const sim=await castle(160,120);
  let state=seed>>>0;
  const rnd=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
  const sample=()=>[(rnd()-.4)*11,6+rnd()*16];
  const floorPoint=()=>{for(;;){const p=sample();if(sim.elevation(...p)!==null)return p;}};
  const small=new OffscreenCanvas(80,60).getContext('2d',{willReadFrequently:true});
  function observe(p){
    sim.render(p);small.drawImage(sim.ctx.canvas,0,0,80,60);
    return small.getImageData(0,0,80,60).data;
  }
  function difference(a,b){
    let sum=0;
    for(let i=0;i<a.length;i+=4)sum+=Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2]);
    return sum/(3*a.length/4);
  }
  try{
    for(let seq=0;seq<count;seq++){
      const anchors=Array.from({length:3},floorPoint);sim.place(anchors,seq%5===4?1:-1);
      let p;
      // Oversample genuinely blocked forward steps. Positions, props and headings are sampled anew.
      for(let attempt=0;attempt<500;attempt++){
        const [x,z]=floorPoint();p={x,z,yaw:rnd()*Math.PI*2};
        if(anchors.some(a=>Math.hypot(x-a[0],z-a[1])<.68))continue;
        if(seq%3!==0||!sim.move({...p},0))break;
      }
      let prev=-1,blocked=false,turnRun=0,queue=[],actions=[],lastTurn=1,regime=0,left=0;
      const history=[],rows=[];
      for(let t=0;t<58;t++){
        const frame=observe(p),diff=history.slice(-3).reverse().map(f=>difference(frame,f));
        while(diff.length<3)diff.push(history.length?difference(frame,history[0]):0);
        history.push(frame);if(history.length>3)history.shift();
        if(!left){regime=(t===0?seq:Math.floor(rnd()*6))%6;left=5+Math.floor(rnd()*15);}
        left--;
        const proposed=[0,t%2?1:2,1,2,Math.floor(rnd()*3),rnd()<.72?0:rnd()<.5?1:2][regime];
        const tail=actions.slice(-3);
        const alternating=tail.length===3&&tail[0]!==0&&tail[1]!==0&&tail[0]===tail[2]&&tail[0]!==tail[1];
        // Reacquire the original heading after taking a lateral path around the edge.
        if(blocked){queue=[2,2,2,2,2,1,1,1,1,1,3,3,3,3,3,1,1,1];}
        else if(!queue.length&&alternating){queue=[2,2,2,2,2];}
        else if(!queue.length&&turnRun>=22){queue=[1,1,1,1,1,1];}
        const label=queue.length?queue.shift():0;
        rows.push({prev,diff,label,blocked});
        const a=label?label-1:proposed;
        const moved=sim.move(p,a);
        blocked=a===0&&!moved;
        turnRun=a!==0&&a===lastTurn?turnRun+1:a!==0?1:0;lastTurn=a;
        actions.push(a);prev=a;
      }
      await emit({seq,rows});
    }
  }finally{sim.dispose();}
}
