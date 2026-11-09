// RGB-D samples accumulate in the world frame of the measured monocular trajectory.
export async function createScan(canvas, layer, onLayer) {
  const [metadata, binary] = await Promise.all(['scan.json','surface.bin'].map(async (name, i) => {
    const response = await fetch(new URL(name, import.meta.url));
    if (!response.ok) throw Error('scan asset unavailable');
    return i ? response.arrayBuffer() : response.json();
  }));
  const context = canvas.getContext('2d');
  const buffer = document.createElement('canvas');
  const back = buffer.getContext('2d');
  const cloud = new DataView(binary);
  let width=1, height=1, scale=1, frameIndex=0, painted=-1, lastCount=-1;
  let yaw=.52, tilt=.36, sparse=false, drag=null, image, depth;
  let cy,sy,ct,st;
  function project(x,y,z) {
    const dx=x+.42, dy=y+.03, dz=z-1.45;
    const side=cy*dx+sy*dz, away=-sy*dx+cy*dz;
    return [width*.51+scale*side,height*.53+scale*(ct*dy-st*away),ct*away+st*dy];
  }
  function line(points,color,weight=1) {
    context.beginPath(); context.strokeStyle=color;context.lineWidth=weight;
    points.forEach(([x,y,z],i) => {
      const p=project(x,y,z);
      if(i) context.lineTo(p[0],p[1]); else context.moveTo(p[0],p[1]);
    });
    context.stroke();
  }
  function reset() {
    const bounds=canvas.getBoundingClientRect();
    if(!bounds.width || !bounds.height) return;
    // Raster resolution is bounded for low-power devices and long scrubbing sessions.
    const dpr=Math.min(devicePixelRatio || 1,1.4,1060/bounds.width);
    width=canvas.width=buffer.width=Math.max(1,Math.round(bounds.width*dpr));
    height=canvas.height=buffer.height=Math.max(1,Math.round(bounds.height*dpr));
    scale=Math.min(width/3.55,height/2.5);
    cy=Math.cos(yaw);sy=Math.sin(yaw);ct=Math.cos(tilt);st=Math.sin(tilt);
    clearPoints();draw(frameIndex,true);
  }
  function clearPoints() {
    image=back.createImageData(width,height);
    depth=new Float32Array(width*height).fill(Infinity);
    lastCount=0;painted=-1;
  }
  function drawPoints(n) {
    if(n<lastCount) clearPoints();
    if(n===lastCount) return;
    const size=Math.max(1,Math.min(4,Math.round(scale*(sparse?.014:.011))));
    for(let i=lastCount;i<n;i++) {
      const off=i*10;
      const xyz=sparse?metadata.sparse[i]:[cloud.getInt16(off,true)/1000,cloud.getInt16(off+2,true)/1000,cloud.getInt16(off+4,true)/1000];
      const [xx,yy,z]=project(...xyz),x=Math.round(xx),y=Math.round(yy);
      if(x<0||x+size>=width||y<0||y+size>=height)continue;
      const r=sparse?176:cloud.getUint8(off+6),g=sparse?230:cloud.getUint8(off+7),b=sparse?197:cloud.getUint8(off+8);
      for(let j=0;j<size;j++)for(let k=0;k<size;k++) {
        const pixel=(y+j)*width+x+k;
        if(depth[pixel]<=z)continue;
        depth[pixel]=z;const at=pixel*4;
        image.data[at]=r;image.data[at+1]=g;image.data[at+2]=b;image.data[at+3]=255;
      }
    }
    back.putImageData(image,0,0);lastCount=n;
  }
  function draw(idx,force=false) {
    frameIndex=Math.min(metadata.frames.length-1,Math.max(0,idx));
    if(!image || (!force && painted===frameIndex))return;
    painted=frameIndex;
    const frame=metadata.frames[frameIndex];
    drawPoints(sparse?metadata.sparse.length:frame[8]);
    context.clearRect(0,0,width,height);
    for(let n=-3;n<=4;n+=.5) {
      line([[n,1.05,-.55],[n,1.05,3.5]],'#b5daca16');
      line([[-3,1.05,n],[1.8,1.05,n]],'#b5daca16');
    }
    context.drawImage(buffer,0,0);
    const path=metadata.frames.slice(0,frameIndex+1).map(row=>row.slice(1,4));
    line(path,'#18251c',4.8);line(path,'#c4fb9c',2);
    const [time,x,y,z,qx,qy,qz,qw]=frame;
    function cameraPoint(u,v,w) {
      // Rotate a local camera-space point by its world_T_camera quaternion.
      const a=2*(qy*w-qz*v),b=2*(qz*u-qx*w),c=2*(qx*v-qy*u);
      return [x+u+qw*a+qy*c-qz*b,y+v+qw*b+qz*a-qx*c,z+w+qw*c+qx*b-qy*a];
    }
    const corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([u,v])=>cameraPoint(u*.104,v*.078,.17));
    line([...corners,corners[0]],'#baff99',1.5);
    corners.forEach(p=>line([[x,y,z],p],'#baff99',1.5));
    const center=project(x,y,z);context.fillStyle='#c8ffa8';context.beginPath();context.arc(center[0],center[1],3,0,2*Math.PI);context.fill();
  }
  layer.onclick=()=> {
    sparse=!sparse;layer.setAttribute('aria-pressed',String(sparse));
    onLayer(sparse);clearPoints();draw(frameIndex,true);
  };
  canvas.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,yaw,tilt};canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove',e=>{
    if(!drag||e.pointerId!==drag.id)return;
    yaw=drag.yaw+(e.clientX-drag.x)*.005;
    tilt=Math.max(-.32,Math.min(1.1,drag.tilt-(e.clientY-drag.y)*.004));reset();
  });
  canvas.addEventListener('lostpointercapture',()=>{drag=null});
  new ResizeObserver(reset).observe(canvas);reset();
  return {seek(seconds){const i=Math.min(metadata.frames.length-1,Math.floor(seconds*metadata.fps));draw(i);return metadata.frames[i][0]}};
}
