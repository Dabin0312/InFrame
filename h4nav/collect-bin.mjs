// Counterfactual supervision. A pair changes only the registered bin's presence.
import {castle} from './castle.mjs';
export async function collectBins(emit,{count=3400,seed=36980911}={}){
 const sim=await castle(160,120);let state=seed;
 const rnd=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
 function point(){for(;;){const pt=[-3+10*rnd(),5.8+16.4*rnd()];if(sim.elevation(...pt)!==null)return pt;}}
 try{
   for(let i=0;i<count;i++){
     const [x,z]=point(),angle=(2*rnd()-1)*Math.PI,d=.51+(i%3===0?2.7+4.2*rnd():2.5*rnd()**1.75);
     const target=[x-d*Math.sin(angle),z-d*Math.cos(angle)];
     if(sim.elevation(...target)===null){i--;continue;}
     const delta=(2*rnd()-1)*(i%5===0?Math.PI:.80);
     const p={x,z,yaw:angle+delta},anchors=[point(),target,point()];
     if(anchors.some((q,k)=>k!==1&&(Math.hypot(q[0]-x,q[1]-z)<.65||Math.hypot(q[0]-target[0],q[1]-target[1])<.65))){i--;continue;}
     sim.place(anchors);sim.render(p);const present=sim.ctx.canvas.toDataURL();
     const labels=sim.labels(p)[1];
     const id=sim.ctx.getImageData(0,0,160,120);
     for(let k=0;k<id.data.length;k+=4){const v=id.data[k+1]>150?255:0;id.data[k]=id.data[k+1]=id.data[k+2]=v;}
     sim.ctx.putImageData(id,0,0);const mask=sim.ctx.canvas.toDataURL();
     sim.place(anchors,1);sim.render(p);const absent=sim.ctx.canvas.toDataURL();
     await emit({i,present,absent,mask,distance:d,pixels:labels.pixels,box:labels.box});
   }
 }finally{sim.dispose();}
}
