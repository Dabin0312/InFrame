import {castle} from './castle.mjs';
export async function collect(n,seed,emit,profile='near'){
  const sim=await castle(160,120),W=160,H=120;
  let state=seed>>>0;const rnd=()=>((state=(Math.imul(1664525,state)+1013904223)>>>0)/4294967296);
  const uniform=(a,b)=>a+(b-a)*rnd();
  function floorPoint(){for(;;){const p=[uniform(-1.6,5.8),uniform(7,22)];if(sim.elevation(...p)!==null)return p;}}
  // Teacher sees the instance-ID pass and true range during demonstration generation only.
  const loop=[[3.9,8.5],[3.8,12],[2.1,15.1],[2,19.4],[-.6,20],[-.6,16],[1.45,13],[.65,9]];
  function sweep(p){
    // Privileged training teacher only. Follow the nearest floor-loop segment with lookahead.
    let best=Infinity,destination;
    for(let j=0;j<loop.length;j++){
      const a=loop[j],b=loop[(j+1)%loop.length],dx=b[0]-a[0],dz=b[1]-a[1],l=Math.hypot(dx,dz);
      const t=Math.max(0,Math.min(.995,((p.x-a[0])*dx+(p.z-a[1])*dz)/(l*l)));
      const e=Math.hypot(p.x-a[0]-t*dx,p.z-a[1]-t*dz);
      if(e<best){best=e;const u=Math.min(1,t+2/l);destination=[a[0]+u*dx,a[1]+u*dz];}
    }
    const target=Math.atan2(p.x-destination[0],p.z-destination[1]);
    const angle=Math.atan2(Math.sin(target-p.yaw),Math.cos(target-p.yaw));
    return Math.abs(angle)<.55?0:1;
  }
  function label(p,k,anchors,stats){
    if(k===3||stats[k].pixels<6)return 1;
    const b=stats[k].box,mid=(b[0]+b[2])/(2*W);
    if(mid<.37)return 1;if(mid>.63)return 2;
    return Math.hypot(p.x-anchors[k][0],p.z-anchors[k][1])<=(profile==='broad'?1.13:1.02)&&stats[k].pixels>=56?3:0;
  }
  try{for(let i=0;i<n;i++){
    const target=i%3,[x,z]=floorPoint();let yaw=uniform(-Math.PI,Math.PI);
    const k=rnd()<.16?3:target,r=rnd(),range=profile==='broad'?(r<.27?uniform(.57,1.17):r<.65?uniform(1.18,2.7):uniform(2.7,6.5)):r<.24?uniform(.60,1.05):r<.50?uniform(1.06,1.60):r<.73?uniform(1.61,3.7):uniform(3.7,9.5);
    const angle=yaw+uniform(-1,1)*(rnd()<.23?Math.PI:.78);
    const anchors=Array.from({length:3},floorPoint);
    anchors[target]=[x-range*Math.sin(angle),z-range*Math.cos(angle)];
    if(sim.elevation(...anchors[target])===null||anchors.some((a,j)=>j!==target&&Math.hypot(a[0]-x,a[1]-z)<.65)){i--;continue;}
    sim.place(anchors);const p={x,z,yaw},rows=[];
    for(let t=0;t<4;t++){
      const rgb=sim.render(p);const photo=sim.ctx.canvas.toDataURL('image/jpeg',.92).split(',')[1],vis=sim.labels(p),a=label(p,k,anchors,vis);
      rows.push({photo,vis,a,sweep:sweep(p),distances:anchors.map(v=>Math.hypot(v[0]-p.x,v[1]-p.z))});
      const roll=rnd();sim.move(p,roll<.64?a:roll<.79?0:roll<.9?1:2);
    }
    await emit({i,k,rows});
  }}finally{sim.dispose();}
}
