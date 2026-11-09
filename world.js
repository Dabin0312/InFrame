import * as T from './engine.js';
// Fixed geometry for the camera simulator. Navigation recovers the object from RGB-D.
const target = {x:2.7,z:-2.5};

const materials = new Map();
function material(color) {
  if (!materials.has(color)) materials.set(color, new T.MeshStandardMaterial({ color, roughness:.68, metalness:.045 }));
  return materials.get(color);
}
const geometries=new Map();
function cached(key, factory) {
  if (!geometries.has(key)) geometries.set(key,factory());
  return geometries.get(key);
}
function mesh(parent,geometry,color,x,y,z) {
  const item=new T.Mesh(geometry,typeof color==='string'?material(color):color);
  item.position.set(x,y,z); item.castShadow=true; item.receiveShadow=true;
  parent.add(item); return item;
}
function box(parent,x,y,z,width,height,depth,color,radius=0) {
  const key=[width,height,depth,radius].join(',');
  const geo=cached(key,()=>radius?new T.RoundedBoxGeometry(width,height,depth,2,radius):new T.BoxGeometry(width,height,depth));
  return mesh(parent,geo,color,x,y,z);
}
function cylinder(parent,x,y,z,top,bottom,h,color,segments=24) {
  return mesh(parent,cached([top,bottom,h,segments,'c'].join(','),()=>new T.CylinderGeometry(top,bottom,h,segments)),color,x,y,z);
}
function pipe(parent,a,b,r,color) {
  const from=new T.Vector3(...a),to=new T.Vector3(...b),axis=to.clone().sub(from);
  const m=cylinder(parent,...from.clone().lerp(to,.5).toArray(),r,r,axis.length(),color,10);
  m.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),axis.normalize());
  return m;
}
const white='#f2f5ff', periwinkle='#969df1', navy='#262953', blue='#474bc7', mint='#70fbd4';
const ink='#262f53',steel='#818da7',light='#cedae6',rubber='#30374d';
function contact(parent,x,z,width,depth,opacity) {
  const shadowCanvas=document.createElement('canvas'); shadowCanvas.width=64; shadowCanvas.height=64;
  const ctx=shadowCanvas.getContext('2d'), gradient=ctx.createRadialGradient(32,32,2,32,32,31);
  gradient.addColorStop(0,'rgba(30,22,92,1)'); gradient.addColorStop(.52,'rgba(38,25,99,.62)'); gradient.addColorStop(1,'rgba(43,31,105,0)');
  ctx.fillStyle=gradient;ctx.fillRect(0,0,64,64);
  const mat=new T.MeshBasicMaterial({map:new T.CanvasTexture(shadowCanvas),transparent:true,opacity,depthWrite:false});
  const item=mesh(parent,new T.PlaneGeometry(width,depth),mat,x,.012,z);
  item.rotation.x=-Math.PI/2;item.castShadow=false;item.renderOrder=1;
}
function floorMark(parent,x,z,width,depth,color,y=.015) {
  const m=box(parent,x,y,z,width,.006,depth,color);m.castShadow=false;return m;
}
function floorFinish(room) {
  const tile=document.createElement('canvas');tile.width=tile.height=1536;
  const ctx=tile.getContext('2d');
  let seed=137;const rand=()=>((seed=Math.imul(seed,1664525)+1013904223>>>0)/4294967296);
  ctx.fillStyle='#a5aba9';ctx.fillRect(0,0,1536,1536);
  for(let i=0;i<65000;i++){
    const gray=Math.floor(70+rand()*145);
    ctx.fillStyle='rgba('+gray+','+gray+','+gray+','+(.11+rand()*.37)+')';
    const x=rand()*1536,y=rand()*1536,r=1+rand()**3*5;
    ctx.beginPath();ctx.moveTo(x-r,y);ctx.lineTo(x+r*.6,y-r*.7);
    ctx.lineTo(x+r,y+r);ctx.lineTo(x-r*.4,y+r*.5);ctx.fill();
  }
  const texture=new T.CanvasTexture(tile);texture.colorSpace=T.SRGBColorSpace;
  texture.anisotropy=4;
  const surface=mesh(room,new T.PlaneGeometry(8,8),new T.MeshStandardMaterial({map:texture,roughness:.94}),0,.007,0);
  surface.rotation.x=-Math.PI/2;surface.castShadow=false;
}
function windowWall(parent){
  // Each pane is inset between dark metal jambs; the pale strips are reflections.
  for (let i=0;i<3;i++) {
    const z=-2.64+i*2.59;
    box(parent,-3.97,1.59,z,.10,1.26,2.35,navy,.035);
    box(parent,-3.89,1.60,z,.07,1.10,2.19,'#65b7e5',.035);
    box(parent,-3.84,1.36,z,.022,.56,2.15,'#91ddec');
    for(const dz of [-.73,.73]) box(parent,-3.82,1.59,z+dz,.045,1.12,.044,white);
    box(parent,-3.80,1.76,z,.045,.038,2.17,white);
    box(parent,-3.79,.95,z,.23,.075,2.48,white,.018);
  }
}
function backWall(parent){
  // A recessed roller shutter, service cabinet, cabling and a goal placard.
  box(parent,-1.85,1.14,-3.95,2.62,2.28,.14,navy,.05);
  box(parent,-1.85,1.12,-3.85,2.42,2.12,.09,blue,.035);
  for(let i=0;i<10;i++) box(parent,-1.85,.21+i*.19,-3.79,2.27,.023,.028,'#9296ff');
  box(parent,-1.85,2.26,-3.80,2.68,.16,.20,light,.025);
  box(parent,-.23,1.18,-3.85,.25,.4,.08,navy,.027);
  box(parent,-.23,1.24,-3.79,.12,.08,.03,mint,.01);
  box(parent,.60,1.30,-3.91,.70,.94,.18,'#bac6df',.045);
  for(let i=0;i<5;i++)box(parent,.60,1.48+i*.059,-3.805,.43,.019,.02,steel);
  box(parent,.80,1.12,-3.80,.045,.14,.025,ink,.01);
  for(const h of [2.48,2.59])pipe(parent,[-3.86,h,-3.88],[3.82,h,-3.88],.027,white);
  for(const x of [-2.8,.2,2.75]) {
    box(parent,x,2.35,-3.79,.67,.105,.11,steel,.025);
    box(parent,x,2.345,-3.72,.54,.055,.045,'#fafff3',.014);
  }
  box(parent,2.7,1.52,-3.88,.50,.59,.07,'#ed5443',.035);
  box(parent,2.7,1.51,-3.835,.14,.28,.025,white,.035);
  box(parent,2.73,1.69,-3.832,.18,.042,.027,white,.014);
  pipe(parent,[2.63,1.62,-3.82],[2.56,1.44,-3.82],.015,white);
}
function storage(parent,x,z,w,h,d,accent){
  const shell=accent?'#8394ec':'#c5d6e5', frame=accent?'#373e83':'#68859c';
  contact(parent,x,z,w*1.65,d*1.75,.52);
  box(parent,x,.09,z,w*.9,.16,d*.9,frame,.04);
  box(parent,x,h*.5,z,w,h*.82,d,shell,.076);
  box(parent,x,h-.08,z,w+.02,.16,d+.025,frame,.037);
  box(parent,x,h-.004,z,w-.10,.037,d-.10,accent?'#b7bdfa':'#e2eef5',.016);
  for(const side of [-1,1]) {
    for(const end of [-1,1])box(parent,x+side*(w/2-.07),h*.49,z+end*(d/2-.025),.11,h*.74,.085,frame,.022);
    box(parent,x+side*w*.25,h*.75,z+d/2+.025,.10,.17,.063,ink,.016);
  }
  box(parent,x,h*.55,z+d/2+.013,w*.32,.11,.039,frame,.02);
  box(parent,x,h*.55,z+d/2+.037,w*.19,.043,.016,navy,.008);
  for(const side of [-1,1])box(parent,x+side*w*.24,h+.016,z,.045,.022,d*.71,frame,.009);
}
function makeTarget(parent){
  const g=new T.Group();g.position.set(target.x,0,target.z);parent.add(g);
  contact(parent,target.x,target.z,.84,.7,.70);
  cylinder(g,0,.10,0,.154,.135,.18,'#c52e32');
  cylinder(g,0,.376,0,.152,.155,.51,'#fd463b');
  cylinder(g,0,.664,0,.105,.153,.075,'#ff5c46');
  cylinder(g,0,.733,0,.047,.103,.067,'#f84935');
  cylinder(g,0,.80,0,.045,.047,.079,steel);
  cylinder(g,0,.39,0,.155,.155,.15,white);
  box(g,0,.39,.155,.106,.051,.012,navy,.008);
  const handle=box(g,.035,.85,0,.23,.042,.065,rubber,.019);handle.rotation.z=-.14;
  box(g,0,.885,0,.20,.027,.05,'#fd7550',.009);
  const gauge=cylinder(g,-.043,.774,.069,.046,.046,.032,white);gauge.rotation.x=Math.PI/2;
  pipe(g,[-.045,.772,.090],[-.024,.796,.090],.004,navy);
  const points=[[-.042,.78,0],[-.138,.801,.038],[-.202,.741,.045],[-.21,.56,.047],[-.205,.34,.056],[-.232,.263,.066]];
  for(let i=1;i<points.length;i++)pipe(g,points[i-1],points[i],.019,rubber);
  return g;
}
function makeRover(){
  const g=new T.Group();
  for(const x of [-.18,.18])for(const z of [-.17,.17]){
    const wheel=cylinder(g,x,.105,z,.105,.105,.081,rubber);wheel.rotation.z=Math.PI/2;
    const hub=cylinder(g,x+Math.sign(x)*.045,.105,z,.058,.058,.014,'#b1b6d9');hub.rotation.z=Math.PI/2;
  }
  box(g,0,.16,0,.35,.15,.47,ink,.052);
  box(g,0,.257,0,.38,.14,.44,white,.059);
  box(g,0,.325,.07,.225,.038,.19,mint,.016);
  box(g,0,.346,-.10,.29,.17,.14,'#ebeaff',.054);
  box(g,0,.348,-.172,.244,.108,.044,navy,.026);
  for(const x of [-.068,.068]){const eye=cylinder(g,x,.351,-.201,.034,.034,.018,mint);eye.rotation.x=Math.PI/2;}
  return g;
}

// Batch immovable pieces that share a material. Keep the target and rover independent for picking and movement.
function batchScenery(group) {
  const sets=new Map();
  for(const child of [...group.children]){
    if(!child.isMesh || child.material.transparent || !child.castShadow)continue;
    const key=child.material;
    if(!sets.has(key))sets.set(key,[]);
    child.updateMatrix();
    const geometry=child.geometry.index?child.geometry.toNonIndexed():child.geometry.clone();
    geometry.applyMatrix4(child.matrix);geometry.clearGroups();
    sets.get(key).push(geometry);
    group.remove(child);
  }
  for(const [mat,parts] of sets){
    const merged=T.mergeGeometries(parts);
    const item=new T.Mesh(merged,mat);item.receiveShadow=true;item.castShadow=true;group.add(item);
    parts.forEach(part=>part.dispose());
  }
}

export class World {
  constructor(canvas) {
    this.renderer=new T.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'low-power'});
    this.renderer.outputColorSpace=T.SRGBColorSpace;
    this.renderer.shadowMap.enabled=true;
    this.renderer.shadowMap.type=T.PCFSoftShadowMap;
    this.renderer.setClearColor(0,0);
    this.scene=new T.Scene();
    this.mapCamera=new T.OrthographicCamera(-6,6,5,-5,.01,70);
    this.eyeCamera=new T.PerspectiveCamera(88,1,.035,42);
    this.room=new T.Group();this.scene.add(this.room);
    this.enclosure=new T.Group();this.room.add(this.enclosure);
    const ambient=new T.HemisphereLight('#fff8f3','#b1acde',2.05);
    const sun=new T.DirectionalLight('#fff3dc',3.0);sun.position.set(-3,11,6);
    sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);
    Object.assign(sun.shadow.camera,{left:-8,right:8,top:8,bottom:-8,near:.5,far:28});sun.shadow.camera.updateProjectionMatrix();
    sun.shadow.normalBias=.024;sun.shadow.bias=-.00025;
    const fill=new T.DirectionalLight('#a2bbff',1.4);fill.position.set(6,5,-3);this.scene.add(ambient,sun,fill);
    const plane=mesh(this.scene,new T.PlaneGeometry(100,100),new T.ShadowMaterial({opacity:.15}),0,-.39,0);
    plane.rotation.x=-Math.PI/2;plane.castShadow=false;
    box(this.room,0,-.20,0,8.28,.35,8.28,'#6266ae',.095);
    for (const x of [-3.6,-2.9,-2.2,2.2,2.9,3.6]) {
      box(this.room,x,-.19,4.142,.40,.054,.014,'#41467b',.008);
    }
    box(this.room,0,-.072,0,8.16,.15,8.16,'#b6bbdf',.036);
    floorFinish(this.room);
    for(let n=-4;n<=4;n++){floorMark(this.room,n,0,.013,8,'#8c98c3');floorMark(this.room,0,n,8,.013,'#8c98c3');}
    for(const side of [-1,1]) {
      floorMark(this.room,0,side*3.75,7.5,.034,'#f2efdf');
      floorMark(this.room,side*3.75,0,.034,7.5,'#f2efdf');
    }
    box(this.room,0,1.38,-4.04,8.22,2.76,.16,'#c3c6f1',.035);
    box(this.room,-4.04,1.38,0,.16,2.76,8.22,'#cfdbf0',.035);
    box(this.room,0,2.775,-4.04,8.29,.13,.24,white,.025);
    box(this.room,-4.04,2.775,0,.24,.13,8.26,white,.025);
    box(this.room,0,.15,-3.92,8.04,.27,.11,periwinkle,.017);
    box(this.room,-3.92,.15,0,.11,.27,8.04,periwinkle,.017);
    windowWall(this.room);backWall(this.room);
    storage(this.room,-.5,0,1.8,1.1,1.2,false);storage(this.room,1.3,.2,.8,.8,1.3,true);
    for(const side of [-1,1]){
      floorMark(this.room,target.x+side*.35,target.z,.045,.71,'#fff5db');
      floorMark(this.room,target.x,target.z+side*.35,.74,.045,'#fff5db');
    }
    // Painted stopping bay and a launch pad sit flush with the floor.
    for(let i=0;i<8;i++){
      const stripe=floorMark(this.room,-2.98+i*.30,-3.53,.11,.39,'#fff1ad',.020);stripe.rotation.y=-.52;
    }
    const pad=cylinder(this.room,-2.8,.018,2.7,.44,.44,.025,'#8ddccf',48);
    pad.castShadow=false;
    const padIn=cylinder(this.room,-2.8,.032,2.7,.34,.34,.012,'#9faecb',48);
    padIn.castShadow=false;
    this.goal=makeTarget(this.room);
    box(this.enclosure,0,1.39,4.04,8.22,2.78,.16,'#ced4ed');
    box(this.enclosure,4.04,1.39,0,.16,2.78,8.22,'#c6ccea');
    box(this.enclosure,0,2.85,0,8.2,.13,8.2,'#dce2f6').castShadow=false;
    for(const s of [-2,2]){box(this.enclosure,s,2.76,0,.19,.03,3.15,white);box(this.enclosure,s,1.35,3.93,.9,1.32,.06,periwinkle,.035);}
    batchScenery(this.room);
    batchScenery(this.enclosure);
    this.robot=makeRover();this.room.add(this.robot);
    this.bearing=new T.Group();
    const ring=mesh(this.bearing,new T.TorusGeometry(.29,.015,6,40),new T.MeshBasicMaterial({color:'#19796b'}),0,.048,0);
    ring.rotation.x=Math.PI/2;ring.castShadow=false;
    const tipShape=new T.Shape();tipShape.moveTo(-.075,0);tipShape.lineTo(.075,0);tipShape.lineTo(0,.17);tipShape.closePath();
    const tip=mesh(this.bearing,new T.ExtrudeGeometry(tipShape,{depth:.005,bevelEnabled:false}),new T.MeshBasicMaterial({color:'#277b70'}),0,.047,-.32);
    tip.rotation.x=-Math.PI/2;tip.castShadow=false;this.room.add(this.bearing);
    this.path=null;this.routeKey='';
    this.ground=new T.Plane(new T.Vector3(0,1,0),0);
    this.raycaster=new T.Raycaster();this.look=new T.Vector3();
  }
  resize(width,height,pixelRatio) {
    this.width=width;this.height=height;
    this.renderer.setPixelRatio(Math.min(1.65,pixelRatio));
    this.renderer.setSize(width,height,false);
    const aspect=width/height, span=Math.max(10.6,13.3/aspect);
    Object.assign(this.mapCamera,{left:-span*aspect/2,right:span*aspect/2,top:span/2,bottom:-span/2});
    this.mapCamera.updateProjectionMatrix();
    this.eyeCamera.aspect=aspect;this.eyeCamera.updateProjectionMatrix();
  }
  updateRoute(points) {
    if(this.routeKey===points)return;
    this.routeKey=points;
    if(this.path){this.room.remove(this.path);this.path.geometry.dispose();this.path.material.dispose();this.path=null;}
    if(!points?.length)return;
    const dots=points.map(p=>new T.Vector3(p.x,.026,p.z));
    this.path=new T.Line(new T.BufferGeometry().setFromPoints(dots),new T.LineBasicMaterial({color:'#3632b2'}));
    this.room.add(this.path);
  }
  floorPoint(nx,ny) {
    this.raycaster.setFromCamera(new T.Vector2(nx,ny),this.mapCamera);
    const hit=this.raycaster.ray.intersectPlane(this.ground,new T.Vector3());
    return hit?{x:hit.x,z:hit.z}:null;
  }
  hitGoal(nx,ny) {
    this.raycaster.setFromCamera(new T.Vector2(nx,ny),this.mapCamera);
    return this.raycaster.intersectObject(this.goal,true).length>0;
  }
  render(state) {
    const {pose,eye,pitch,mapAngle,routePoints}=state;
    this.updateRoute(routePoints);
    this.robot.visible=!eye;this.bearing.visible=!eye;this.enclosure.visible=eye;
    this.bearing.position.set(pose.x,0,pose.z);this.bearing.rotation.y=-pose.yaw;
    this.robot.position.set(pose.x,.014,pose.z);this.robot.rotation.y=-pose.yaw;
    const cam=eye?this.eyeCamera:this.mapCamera;
    if(eye){
      cam.position.set(pose.x,.78,pose.z);
      cam.lookAt(pose.x+Math.sin(pose.yaw)*Math.cos(pitch),.78+Math.sin(pitch),pose.z-Math.cos(pose.yaw)*Math.cos(pitch));
      this.scene.background=new T.Color('#dcdcf7');
    }else{
      const angle=.60+mapAngle;
      cam.position.set(12*Math.sin(angle),10.5,12*Math.cos(angle));
      const followX=(pose.x+2.8)*.045, followZ=(pose.z-2.7)*.045;
      cam.position.x+=followX;cam.position.z+=followZ;
      cam.lookAt(followX,1.18,followZ);
      this.scene.background=null;
    }
    this.renderer.render(this.scene,cam);
    const label=this.look.set(target.x,1.03,target.z).project(cam);
    const goalPixel={x:(label.x+1)*this.width/2,y:(1-label.y)*this.height/2};
    const player=this.look.set(pose.x,0,pose.z).project(cam);
    goalPixel.player=[(player.x+1)*this.width/2,(1-player.y)*this.height/2];
    return goalPixel;
  }
}
