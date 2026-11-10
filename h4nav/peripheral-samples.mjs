// Seeded poses shared by the RGB renderer and the training-only route teacher.
export function* peripheralSamples(elevation,count=7200,seed=541337){
  let state=seed>>>0;
  const rnd=()=>((state=(Math.imul(state,1664525)+1013904223)>>>0)/4294967296);
  function floorPoint(){for(;;){const p=[-2.6+rnd()*9.4,6+rnd()*16.4];if(elevation(...p)!==null)return p;}}
  for(let i=0;i<count;i++){
      const [x,z]=floorPoint(),anchors=Array.from({length:3},floorPoint);
      const r=rnd(),distance=.57+Math.pow(rnd(),1.25)*8,theta=(rnd()*2-1)*Math.PI;
      anchors[2]=[x-distance*Math.sin(theta),z-distance*Math.cos(theta)];
      if(elevation(...anchors[2])===null||anchors.some((a,j)=>j<2&&Math.hypot(x-a[0],z-a[1])<.5)){i--;continue;}
      const offset=(rnd()<.5?-1:1)*(r<.35?.42+rnd()*.39:r<.8?rnd()*.5:rnd()*Math.PI);
      const p={x,z,yaw:theta+offset},removed=rnd()<.24?2:-1;
      yield {i,p,anchors,removed,distance};
  }
}
