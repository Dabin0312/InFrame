// Habitat floor triangles use X/Z for the plan view and Y for elevation.
function barycentric([a,b,c],x,z) {
  const d=(b[2]-c[2])*(a[0]-c[0])+(c[0]-b[0])*(a[2]-c[2]);
  if(Math.abs(d)<1e-9) return null;
  const u=((b[2]-c[2])*(x-c[0])+(c[0]-b[0])*(z-c[2]))/d;
  const v=((c[2]-a[2])*(x-c[0])+(a[0]-c[0])*(z-c[2]))/d;
  return [u,v,1-u-v];
}

export function floorHeight(tris,x,z) {
  for(const tri of tris) {
    const weights=barycentric(tri,x,z);
    if(weights && weights.every(w=>w>=-1e-5)) return weights.reduce((h,w,i)=>h+w*tri[i][1],0);
  }
  return null;
}

// Clip the direct X/Z segment to each triangle. A continuous chain across the
// floor gives a traversable upper bound on the shortest path to this viewpoint.
export function directFloorLength(tris, start, end) {
  const spans=[];
  for(const tri of tris) {
    const a=barycentric(tri,start[0],start[2]), b=barycentric(tri,end[0],end[2]);
    if(!a || !b) continue;
    let lo=0,hi=1;
    for(let i=0;i<3;i++) {
      const slope=b[i]-a[i];
      if(Math.abs(slope)<1e-10) { if(a[i]<-1e-7) hi=-1; }
      else if(slope>0) lo=Math.max(lo,-a[i]/slope);
      else hi=Math.min(hi,-a[i]/slope);
    }
    if(hi<=lo) continue;
    const elevation=t=>a.reduce((y,w,i)=>y+(w+t*(b[i]-w))*tri[i][1],0);
    spans.push({lo,hi,elevation});
  }
  spans.sort((a,b)=>a.lo-b.lo);
  const flat=Math.hypot(end[0]-start[0],end[2]-start[2]);
  let t=0,y=start[1],length=0;
  for(const span of spans) {
    if(span.hi<=t) continue;
    if(span.lo>t+1e-7) return Infinity;
    const first=span.elevation(t), last=span.elevation(span.hi);
    if(Math.abs(first-y)>.001) continue;
    length+=Math.abs(first-y)+Math.hypot((span.hi-t)*flat,last-first);
    y=last;t=span.hi;
    if(t>=1-1e-8 && Math.abs(y-end[1])<=.001) return length+Math.abs(y-end[1]);
  }
  return Infinity;
}

export function viewpointRange(tris,start,views,radius=.8) {
  // 3D Euclidean distance is a lower bound on every floor path.
  const lower=Math.min(...views.map(v=>Math.hypot(...v.map((n,i)=>n-start[i]))));
  if(lower>radius) return {kind:'outside',distance:lower};
  const upper=Math.min(...views.map(v=>directFloorLength(tris,start,v)));
  return upper<=radius ? {kind:'within',distance:upper} : {kind:'unresolved'};
}
