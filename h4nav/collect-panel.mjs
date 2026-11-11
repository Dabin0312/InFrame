// RGB is the student input. Object masks, camera poses and anchors are offline supervision only.
import {castle} from './castle.mjs';

export async function collectPanel(emit, {count=6200, seed=872165, targetIndex=1}={}) {
  let state=seed;
  const random=()=>((state=(Math.imul(1664525,state)+1013904223)>>>0)/4294967296);
  const sim=await castle(160,120);
  function point(panel=false) {
    for (;;) {
      const x=panel ? 4.9+2.2*random() : -3.1+10.4*random();
      const z=panel ? 7+5*random() : 5.8+16.3*random();
      if(sim.elevation(x,z)!==null) return [x,z];
    }
  }
  try {
    for(let i=0;i<count;) {
      const [x,z]=point(i%4===0);
      const near=targetIndex===0 && i%4===2;
      const d=near ? .60+1.55*random() : .6+9.0*random(), a=2*Math.PI*random();
      const target=[x-d*Math.sin(a),z-d*Math.cos(a)];
      if(sim.elevation(...target)===null) continue;
      const yaw=a+(random()-.5)*(i%4===1?Math.PI*2:1.62);
      const p={x,z,yaw}, anchors=[point(),target,point()];
      if(targetIndex===0) [anchors[0],anchors[1]]=[anchors[1],anchors[0]];
      const removed=i%9===0?targetIndex:-1;
      if(anchors.some(q=>Math.hypot(x-q[0],z-q[1])<.55)) continue;
      async function observation(absent) {
        sim.place(anchors,absent);
        sim.render(p);
        const rgb=sim.ctx.canvas.toDataURL();
        const label=sim.labels(p)[targetIndex], mask=sim.ctx.getImageData(0,0,160,120);
        for(let j=0;j<mask.data.length;j+=4) {
          const value=mask.data[j+targetIndex]>150?255:0;
          mask.data[j]=mask.data[j+1]=mask.data[j+2]=value;
        }
        sim.ctx.putImageData(mask,0,0);
        return {rgb,mask:sim.ctx.canvas.toDataURL(),p,anchors,removed:absent,...label};
      }
      const item=await observation(removed);
      await emit({i,...item});
      if(targetIndex===0 && removed<0 && i%3===0) {
        await emit({i:count+i,pairedWith:i,...await observation(0)});
      }
      i++;
    }
  } finally {sim.dispose();}
}
