// Generate training-only RGB, occlusion-aware instance masks, and approach labels in Castle.
import {castle} from './castle.mjs';
import {peripheralSamples} from './peripheral-samples.mjs';
export async function collectPeripheral(emit,{count=7200,seed=541337}={}){
  const sim=await castle(160,120);
  try{
    for(const {i,p,anchors,removed,distance} of peripheralSamples(sim.elevation,count,seed)){
      sim.place(anchors,removed);
      sim.render(p);const rgb=sim.ctx.canvas.toDataURL('image/png').split(',')[1];
      const image=sim.render(p,true),pix=image.data;
      // Preserve every foreground pixel in the binary label.
      for(let j=0;j<pix.length;j+=4){const value=pix[j+2]>150?255:0;pix[j]=pix[j+1]=pix[j+2]=value;}
      sim.ctx.putImageData(image,0,0);
      await emit({i,rgb,mask:sim.ctx.canvas.toDataURL('image/png').split(',')[1],distance});
    }
  }finally{sim.dispose();}
}
