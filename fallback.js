import {target,clamp} from './navigation.js?room=1';

// Geometry of the source room is used only for this optional software renderer.
const obstacles=[{x:-.5,z:0,width:1.8,depth:1.2},{x:1.3,z:.2,width:.8,depth:1.3},{x:2.7,z:-2.5,width:.36,depth:.36}];
const colors={back:'#c7caff',side:'#999fe9',roof:'#eeefff',floor:'#b0b8ea',rim:'#7176bd',crate:'#9cabc8',edge:'#32355d',goal:'#ff5140'};
export class CanvasWorld {
  constructor(canvas){this.ctx=canvas.getContext('2d');this.canvas=canvas;}
  resize(width,height,dpr){
    this.width=width;this.height=height;this.dpr=Math.min(1.5,dpr);
    this.canvas.width=Math.floor(width*this.dpr);this.canvas.height=Math.floor(height*this.dpr);
  }
  project(x,y,z){
    const {angle,scale,width,height}=this;
    return [(x*Math.cos(angle)-z*Math.sin(angle))*scale+width/2,
      height/2+((x*Math.sin(angle)+z*Math.cos(angle))*.60-(y-1.18)*.80)*scale];
  }
  floorPoint(nx,ny){
    const sx=nx*this.width/(2*this.scale),sz=(-ny*this.height/(2*this.scale)-1.18*.8)/.60;
    return {x:sx*Math.cos(this.angle)+sz*Math.sin(this.angle),z:-sx*Math.sin(this.angle)+sz*Math.cos(this.angle)};
  }
  hitGoal(nx,ny){
    const p=this.project(target.x,.50,target.z);
    return Math.hypot(p[0]-(nx+1)*this.width/2,p[1]-(1-ny)*this.height/2)<13;
  }
  face(points,color,stroke){
    const c=this.ctx;c.beginPath();
    points.forEach((p,i)=>{const px=this.project(...p);if(i)c.lineTo(...px);else c.moveTo(...px)});
    c.closePath();c.fillStyle=color;c.fill();if(stroke){c.strokeStyle=stroke;c.lineWidth=.7;c.stroke();}
  }
  block(x,z,w,h,d,c,y=0){
    const a=x-w/2,b=x+w/2,f=z-d/2,g=z+d/2,top=h+y;
    this.face([[a,y,g],[b,y,g],[b,top,g],[a,top,g]],c[0]);
    this.face([[b,y,f],[b,y,g],[b,top,g],[b,top,f]],c[1]);
    this.face([[a,top,f],[b,top,f],[b,top,g],[a,top,g]],c[2]);
  }
  line(points,color,width=1){
    const c=this.ctx;c.beginPath();points.forEach((p,i)=>{const xy=this.project(...p);if(i)c.lineTo(...xy);else c.moveTo(...xy)});
    c.strokeStyle=color;c.lineWidth=width;c.stroke();
  }
  map(state){
    const {pose,mapAngle,routePoints}=state;
    this.angle=.60+mapAngle;this.scale=Math.min(this.width/13.3,this.height/10.6);
    const c=this.ctx;c.shadowColor='#6564a65c';c.shadowBlur=16;c.shadowOffsetY=9;
    this.block(0,0,8.18,.28,8.18,[colors.rim,colors.rim,colors.floor],-.28);
    c.shadowBlur=0;c.shadowOffsetY=0;
    for(let n=-4;n<=4;n++){this.line([[n,.01,-4],[n,.01,4]],'#9ba5d8');this.line([[-4,.01,n],[4,.01,n]],'#9ba5d8')}
    this.block(0,-4,8.18,2.76,.16,[colors.back,colors.side,colors.roof]);
    this.block(-4,0,.16,2.76,8.18,[colors.side,colors.back,colors.roof]);
    for(let i=-1;i<=1;i++){
      this.block(-3.86,i*2.57,.08,1.18,2.24,['#527fae','#76cbeb','#f0f5ff'],1.02);
      this.block(-3.79,i*2.57,.16,.06,2.36,[colors.side,'#dbeaf8',colors.roof],.96);
    }
    this.block(-1.8,-3.85,2.4,2.15,.1,['#7276d8',colors.side,colors.roof]);
    for(let y=.2;y<2.1;y+=.19)this.line([[-2.92,y,-3.78],[-.68,y,-3.78]],'#a2a8f2');
    this.block(2.7,-3.88,.5,.55,.07,['#fc5a4a',colors.side,'#ffe1d3'],1.25);
    if(routePoints?.length)this.line(routePoints.map(p=>[p.x,.02,p.z]),'#5450ce',1.6);
    const visible=[
      {x:obstacles[0].x,z:obstacles[0].z,draw:()=>this.block(-.5,0,1.8,1.1,1.2,['#a2b4c8','#7e96b1','#e2ebf4'])},
      {x:obstacles[1].x,z:obstacles[1].z,draw:()=>this.block(1.3,.2,.8,.8,1.3,['#848dd7','#6c76bd','#bfc3fa'])},
      {...target,draw:()=>{
        this.block(target.x,target.z,.26,.78,.28,['#ff604b','#d23d36','#fd9076']);
        this.block(target.x,target.z,.28,.13,.30,['#fff1e3','#dfd3c7','#fff'],.34);
        this.block(target.x,target.z,.26,.06,.10,[colors.edge,colors.edge,colors.rim],.81);
      }},
      {...pose,draw:()=>{
        this.block(pose.x,pose.z,.40,.27,.44,[colors.rim,colors.edge,colors.roof]);
        this.block(pose.x,pose.z,.28,.11,.25,['#50baa3',colors.edge,'#6ffed5'],.27);
        this.line([[pose.x,.32,pose.z],[pose.x+Math.sin(pose.yaw)*.51,.32,pose.z-Math.cos(pose.yaw)*.51]],'#253c66',2);
      }}
    ];
    visible.sort((a,b)=>(a.x-b.x)*Math.sin(this.angle)+(a.z-b.z)*Math.cos(this.angle)).forEach(item=>item.draw());
    const [x,y]=this.project(target.x,1.03,target.z);return {x,y,player:this.project(pose.x,0,pose.z)};
  }
  firstPerson({pose,pitch}) {
    const c=this.ctx,w=this.width,h=this.height,focus=h/(2*Math.tan(88*Math.PI/360)),horizon=h/2+Math.tan(pitch)*focus;
    c.fillStyle='#dfe5ff';c.fillRect(0,0,w,h);c.fillStyle='#aab4d9';c.fillRect(0,horizon,w,h-horizon);
    const boxes=[
      {x:0,z:-4.04,width:8.2,depth:.14,height:2.76,color:'#bcbfee'},
      {x:0,z:4.04,width:8.2,depth:.14,height:2.76,color:'#ced5ef'},
      {x:-4.04,z:0,width:.14,depth:8.2,height:2.76,color:'#a1b3e1'},
      {x:4.04,z:0,width:.14,depth:8.2,height:2.76,color:'#c5cbea'},
      {...obstacles[0],height:1.1,color:'#849caf'}, {...obstacles[1],height:.8,color:'#727bd1'},
      {...obstacles[2],height:.88,color:'#fa5140',goal:true}
    ];
    const step=Math.max(2,Math.floor(w/340));
    for(let col=0;col<w;col+=step){
      const offset=(col-w/2)/focus,dx=Math.sin(pose.yaw)+Math.cos(pose.yaw)*offset,dz=-Math.cos(pose.yaw)+Math.sin(pose.yaw)*offset;
      const hits=[];
      for(const b of boxes){
        const tx1=(b.x-b.width/2-pose.x)/(dx||.000001),tx2=(b.x+b.width/2-pose.x)/(dx||.000001);
        const tz1=(b.z-b.depth/2-pose.z)/(dz||.000001),tz2=(b.z+b.depth/2-pose.z)/(dz||.000001);
        const near=Math.max(Math.min(tx1,tx2),Math.min(tz1,tz2)),far=Math.min(Math.max(tx1,tx2),Math.max(tz1,tz2));
        if(far>=near && near>.025)hits.push({b,near});
      }
      hits.sort((a,b)=>b.near-a.near);
      for(const {b,near} of hits){
        const y=horizon-(b.height-.78)*focus/near;
        c.fillStyle=b.color;c.fillRect(col,y,step+1,b.height*focus/near);
        if(b.goal){c.fillStyle='#fff2df';c.fillRect(col,horizon+.30*focus/near,step+1,.13*focus/near);}
        c.fillStyle='rgba(57,64,114,'+clamp(near/65,0,.15)+')';c.fillRect(col,y,step+1,b.height*focus/near);
      }
    }
  }
  render(state){
    this.ctx.setTransform(this.dpr,0,0,this.dpr,0,0);this.ctx.clearRect(0,0,this.width,this.height);
    if(state.eye){this.firstPerson(state);return null}
    return this.map(state);
  }
}
