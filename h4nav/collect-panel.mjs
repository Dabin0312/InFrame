// RGB is the student input. Object masks, camera poses and anchors are offline supervision only.
import {castle} from './castle.mjs';

export async function collectPanel(emit, {count=6200, seed=872165}={}) {
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
      const d=.6+9.0*random(), a=2*Math.PI*random();
      const target=[x-d*Math.sin(a),z-d*Math.cos(a)];
      if(sim.elevation(...target)===null) continue;
      const yaw=a+(random()-.5)*(i%4===1?Math.PI*2:1.62);
      const p={x,z,yaw}, anchors=[point(),target,point()], removed=i%9===0?1:-1;
      if(anchors.some(q=>Math.hypot(x-q[0],z-q[1])<.55)) continue;
      sim.place(anchors,removed);
      sim.render(p);
      const rgb=sim.ctx.canvas.toDataURL();
      const label=sim.labels(p)[1], mask=sim.ctx.getImageData(0,0,160,120);
      for(let j=0;j<mask.data.length;j+=4) {
        const value=mask.data[j+1]>150?255:0;
        mask.data[j]=mask.data[j+1]=mask.data[j+2]=value;
      }
      sim.ctx.putImageData(mask,0,0);
      await emit({i,rgb,mask:sim.ctx.canvas.toDataURL(),p,anchors,removed,...label});
      i++;
    }
  } finally {sim.dispose();}
}
