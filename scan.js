import {episode} from './episode.js';
// Registered depth accumulates in the metric world frame of the estimated RGB-D trajectory.
export async function createScan(canvas, layer, onLayer) {
  const [metadata, binary] = await Promise.all(['scan.json?room=1','surface.bin?room=1'].map(async (name, i) => {
    const response = await fetch(new URL(name, import.meta.url));
    if (!response.ok) throw Error('scan asset unavailable');
    return i ? response.arrayBuffer() : response.json();
  }));
  if(metadata.scene!==episode.scene)throw Error('Map and route refer to different scenes');
  const context = canvas.getContext('2d');
  const buffer = document.createElement('canvas');
  const back = buffer.getContext('2d');
  const cloud = new DataView(binary);
  let width=1, height=1, scale=1, frameIndex=0, painted=-1, lastCount=-1;
  let yaw=-.50, tilt=.64, sparse=false, drag=null, image, depth, drivePose=null;
  let cy,sy,ct,st;
  function project(x,y,z) {
    const dx=x-.1, dy=.47-y, dz=-z-.65;
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
    scale=Math.min(width/9.2,height/6.35);
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
    const size=Math.max(1,Math.min(4,Math.round(scale*(sparse?.026:.028))));
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
    for(let n=-4;n<=4;n+=1) {
      line([[n,-.01,-4],[n,-.01,4]],'#b5daca28');
      line([[-4,-.01,n],[4,-.01,n]],'#b5daca28');
    }
    context.drawImage(buffer,0,0);
    if(drivePose){
      const path=episode.route.map(([x,z])=>[x,.04,z]);
      line(path,'#111f1a',5);line(path,'#cdff9c',2.4);
      const {x,z,yaw}=drivePose;
      const ground=project(x,.08,z),head=project(x+.41*Math.sin(yaw),.08,z-.41*Math.cos(yaw));
      const angle=Math.atan2(head[1]-ground[1],head[0]-ground[0]);
      context.save();context.translate(ground[0],ground[1]);context.rotate(angle);
      context.fillStyle='#f6fff0';context.strokeStyle='#294333';context.lineWidth=2;
      context.beginPath();context.moveTo(10,0);context.lineTo(-6,6);context.lineTo(-3,0);context.lineTo(-6,-6);context.closePath();context.fill();context.stroke();context.restore();
    }
    if(frameIndex>=episode.targetFirstFrame){
      const p=project(...episode.target);
      context.beginPath();context.arc(p[0],p[1],5.5,0,Math.PI*2);context.fillStyle='#ff7c53';context.fill();context.strokeStyle='#321e18';context.lineWidth=2;context.stroke();
      context.font='600 13px Geist,InframeHangul,sans-serif';const label='소화기';
      const tw=context.measureText(label).width,tx=Math.max(3,Math.min(width-tw-12,p[0]+9)),ty=p[1]-17;
      context.fillStyle='#242620eb';context.fillRect(tx-3,ty-12,tw+9,20);context.fillStyle='#ffb693';context.fillText(label,tx+1,ty+3);
    }
    if(drivePose)return;
    const path=metadata.frames.slice(0,frameIndex+1).map(row=>row.slice(1,4));
    line(path,'#18251c',4.8);line(path,'#c4fb9c',2);
    const [time,x,y,z,qx,qy,qz,qw]=frame;
    function cameraPoint(u,v,w) {
      // Rotate a local camera-space point by its world_T_camera quaternion.
      const a=2*(qy*w-qz*v),b=2*(qz*u-qx*w),c=2*(qx*v-qy*u);
      return [x+u+qw*a+qy*c-qz*b,y+v+qw*b+qz*a-qx*c,z+w+qw*c+qx*b-qy*a];
    }
    const corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([u,v])=>cameraPoint(u*.22,v*.155,.30));
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
  return {
    seek(seconds){
      const changed=drivePose!==null;drivePose=null;
      const i=Math.min(metadata.frames.length-1,Math.floor(seconds*metadata.fps));draw(i,changed);return metadata.frames[i][0];
    },
    navigate(pose){
      if(drivePose===pose)return;
      drivePose=pose;draw(metadata.frames.length-1,true);
    }
  };
}
