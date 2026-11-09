// The trajectory is from Habitat-Sim. The architectural point drawing and camera aim are illustrative.
(() => {
'use strict';
const by=id=>document.getElementById(id), host=by('scene'), canvas=by('view'), ctx=canvas.getContext('2d');
if(!ctx)return;
const reduce=matchMedia('(prefers-reduced-motion: reduce)'), coarse=matchMedia('(hover: none)');
const route=[[-2.8,0,2.7],[1.9000002,.1999995,1.0999992],[2.0000002,.1999995,.9499992],[2.7,0,-2]], target=[2.7,.56,-2.5];
const vadd=(a,b)=>a.map((v,i)=>v+b[i]), sub=(a,b)=>a.map((v,i)=>v-b[i]), mul=(v,k)=>v.map(x=>x*k), mix=(a,b,k)=>vadd(a,mul(sub(b,a),k)), norm=v=>Math.hypot(...v), clamp=(v,a,b)=>Math.max(a,Math.min(b,v)), ease=v=>v*v*(3-2*v), dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const segments=route.slice(1).map((p,i)=>norm(sub(p,route[i]))), length=segments.reduce((a,b)=>a+b);
let seed=75;function rnd(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
const pts=[], lines=[], solids=[],nearPts=[],nearLines=[],nearSolids=[];
let dst=[pts,lines,solids];
const palette={plaster:[.75,.81,.75],side:[.56,.68,.64],trim:[.85,.88,.78],floor:[.52,.65,.61],metal:[.67,.77,.72],glass:[.35,.54,.53],shadow:[.30,.43,.40],orange:[1,.48,.23],white:[.93,.93,.79]};
function vert(buf,p,c,b=1,s=1){buf.push(...p,c[0]*b,c[1]*b,c[2]*b,s)}
function line(a,b,col='trim',brightness=.57){let c=palette[col];vert(dst[1],a,c,brightness);vert(dst[1],b,c,brightness)}
function poly(a,u,v,col,den=18,level=.85,solid=.13){
 const c=palette[col],b=vadd(a,u),d=vadd(a,v),e=vadd(b,v);
 if(solid>0)for(const p of [a,b,d,b,e,d])vert(dst[2],p,c,solid);
 const nu=Math.max(2,Math.ceil(norm(u)*den)),nv=Math.max(2,Math.ceil(norm(v)*den*.9));
 for(let j=0;j<=nv;j++){const scan=(.82+.18*Math.sin(j*1.07));for(let i=0;i<=nu;i++){
 if(rnd()<.17)continue;const x=(i+(rnd()-.5)*.9)/nu,y=(j+(rnd()-.5)*.74)/nv;
 const p=vadd(vadd(a,mul(u,x)),mul(v,y)),cloud=.90+.12*Math.sin(2.7*p[0]+1.8*p[2])*Math.cos(p[1]*3.2),bri=level*cloud*scan*(.44+.61*rnd());vert(dst[0],p,c,bri,.60+.67*rnd());}}
}
function frame(a,u,v,c,b=.7){let k=vadd(a,u),l=vadd(a,v),m=vadd(k,v);line(a,k,c,b);line(k,m,c,b);line(m,l,c,b);line(l,a,c,b)}
function box(x,y,z,w,h,d,c='metal',den=23){let a=x-w/2,b=z-d/2;poly([a,y,b+d],[w,0,0],[0,h,0],c,den,.78,.17);poly([a+w,y,b],[0,0,d],[0,h,0],c,den,.62,.14);poly([a,y,b],[0,0,d],[0,h,0],c,den,.57,.13);poly([a,y,b],[w,0,0],[0,h,0],c,den,.57,.13);poly([a,y+h,b],[w,0,0],[0,0,d],c,den,1.05,.22);frame([a,y+h,b],[w,0,0],[0,0,d],c,.72)}
// A cutaway of the eight-metre room. Window, panel and pipe marks are render details.
poly([-4,0,-4],[8,0,0],[0,0,8],'floor',22,.72,.155);
for(let i=-4;i<=4.01;i+=.5){line([i,.008,-4],[i,.008,4],'floor',i%1===0?.40:.26);line([-4,.008,i],[4,.008,i],'floor',i%1===0?.40:.26)}
frame([-4,.012,-4],[8,0,0],[0,0,8],'trim',.78);
poly([-4,0,-4],[8,0,0],[0,2.8,0],'plaster',25,.95,.175);
poly([-4,0,-4],[0,0,8],[0,2.8,0],'side',25,.92,.17);
frame([-4,0,-4],[8,0,0],[0,2.8,0],'trim');frame([-4,0,-4],[0,0,8],[0,2.8,0],'metal');
for(let k=0;k<4;k++){let z=-3.83+k*1.94;
 poly([-3.975,.92,z],[0,0,1.75],[0,1.32,0],'glass',21,.60,.23);
 frame([-3.95,.91,z],[0,0,1.76],[0,1.34,0],'white',.93);
 for(let m=0;m<3;m++){let x=z+(m+1)*.44;line([-3.94,.92,x],[-3.94,2.25,x],'metal',.71)}
 line([-3.94,1.85,z],[-3.94,1.85,z+1.76],'trim',.72);
 for(let j=1;j<8;j++)line([-3.94,.94+j*.15,z],[-3.94,.94+j*.15,z+1.75],'glass',.52);
}
for(const h of [.12,.19,2.54,2.64,2.73]){line([-3.97,h,-3.97],[3.97,h,-3.97],'trim',.78);line([-3.97,h,-3.97],[-3.97,h,3.96],'trim',.68)}
for(let x=-3.7;x<3.8;x+=.86)line([x,.21,-3.982],[x,2.5,-3.982],'side',.65);
for(const x of [-2.64,.43]){
 poly([x,.03,-3.955],[1.08,0,0],[0,2.2,0],'shadow',27,.95,.52);frame([x,.03,-3.93],[1.08,0,0],[0,2.2,0],'white',.97);
 frame([x+.12,1.32,-3.92],[.80,0,0],[0,.68,0],'metal',.75);line([x+.78,.96,-3.91],[x+1,.96,-3.91],'white',1);
}
for(let i=0;i<4;i++){const x=-.99+(i%2)*.45,y=1.05+Math.floor(i/2)*.52;
 poly([x,y,-3.94],[.35,0,0],[0,.44,0],'metal',32,1,.35);for(let j=1;j<6;j++)line([x+.04,y+.05*j,-3.925],[x+.28,y+.05*j,-3.925],'trim',.65)}
box(-.5,0,0,1.8,1.1,1.2);box(1.3,0,.2,.8,.8,1.3,'metal');
for(const [cx,cz,w,h,d] of [[-.5,0,1.8,1.1,1.2],[1.3,.2,.8,.8,1.3]]){
 for(let y=.14;y<h-.09;y+=.19){line([cx-w*.46,y,cz+d/2+.012],[cx+w*.46,y,cz+d/2+.012],'trim',.88);line([cx+w/2+.012,y,cz-d*.44],[cx+w/2+.012,y,cz+d*.44],'shadow',.83)}
 for(let j=0;j<9;j++)line([cx-w*.47+j*w*.11,h+.012,cz-d*.44],[cx-w*.47+j*w*.11,h+.012,cz+d*.44],'shadow',.9)
}
// Orange target occupies the proxy's footprint; detail is illustrative, not sensor data.
function cylinder(cx,cz,profile){for(let j=0;j<profile.length-1;j++){let [ya,ra]=profile[j],[yb,rb]=profile[j+1];for(let i=0;i<48;i++){
 const a=i*Math.PI/24,b=(i+1)*Math.PI/24,p=[cx+Math.cos(a)*ra,ya,cz+Math.sin(a)*ra],q=[cx+Math.cos(b)*ra,ya,cz+Math.sin(b)*ra],r=[cx+Math.cos(a)*rb,yb,cz+Math.sin(a)*rb],s=[cx+Math.cos(b)*rb,yb,cz+Math.sin(b)*rb],br=.54+.27*Math.cos(a-.65);
 for(let k of [p,q,r,q,s,r])vert(solids,k,palette.orange,br);for(let k=0;k<18;k++)vert(pts,mix(mix(p,q,rnd()),mix(r,s,rnd()),rnd()),palette.orange,.65+.45*rnd(),1.15);
 }}}
cylinder(2.7,-2.5,[[.03,.10],[.07,.15],[.63,.15],[.72,.13],[.78,.055],[.88,.047]]);
box(2.73,.86,-2.5,.24,.055,.065,'orange',32);line([2.65,.82,-2.48],[2.51,.70,-2.47],'white',.96);line([2.51,.70,-2.47],[2.52,.29,-2.46],'shadow',1.35);
// Printed band, squeeze lever and the curved hose distinguish the cylinder at camera height.
for(let j=0;j<22;j++){const a=.72+j*.071,b=a+.071,pa=[2.7+Math.cos(a)*.153,.35,-2.5+Math.sin(a)*.153],pb=[2.7+Math.cos(b)*.153,.35,-2.5+Math.sin(b)*.153];poly(pa,sub(pb,pa),[0,.17,0],'white',50,.92,.89)}
for(const yy of [.389,.414,.446]) line([2.635,yy,-2.355],[2.76,yy,-2.349],'shadow',.72);
box(2.67,.904,-2.5,.24,.033,.056,'shadow',36);box(2.59,.875,-2.498,.035,.053,.059,'trim',35);
let hose=[[2.63,.82,-2.458],[2.54,.825,-2.43],[2.485,.78,-2.425],[2.47,.64,-2.42],[2.464,.44,-2.426],[2.455,.32,-2.435],[2.438,.27,-2.438]];
for(let j=1;j<hose.length;j++){let a=hose[j-1],b=hose[j];for(let k=0;k<14;k++){let t=k*Math.PI/7,u=(k+1)*Math.PI/7,d=[.017*Math.cos(t),0,.017*Math.sin(t)],e=[.017*Math.cos(u),0,.017*Math.sin(u)];for(const p of [vadd(a,d),vadd(b,d),vadd(a,e),vadd(a,e),vadd(b,d),vadd(b,e)])vert(solids,p,palette.metal,.41+.24*Math.sin(t));}}
for(let k=0;k<32;k++){let a=k*Math.PI/16,b=(k+1)*Math.PI/16;let p=[2.68+.047*Math.cos(a),.804+.047*Math.sin(a),-2.438],q=[2.68+.047*Math.cos(b),.804+.047*Math.sin(b),-2.438];for(let x of [[2.68,.804,-2.438],p,q])vert(solids,x,palette.white,.96);line(p,q,'metal',.88)}
line([2.68,.803,-2.436],[2.696,.827,-2.436],'shadow',.42);
dst=[nearPts,nearLines,nearSolids];
poly([-4,0,4],[8,0,0],[0,2.8,0],'plaster',20,.9,.19);poly([4,0,-4],[0,0,8],[0,2.8,0],'side',20,.8,.20);
for(let i=-4;i<=4;i++){line([i,0,3.98],[i,2.8,3.98],'metal',.7);line([3.98,0,i],[3.98,2.8,i],'metal',.7)}
dst=[pts,lines,solids];
const reduced=()=>reduce.matches;
let w=0,h=0,dpr=1,progress=0,playing=false,eye=false,reverse=false,yawFlip=0,hoverX=0,hoverY=0,smX=0,smY=0,active=true,raf=0,last=0,age=0,rendered=false;
const gpu=document.createElement('canvas');let gl=null;try{gl=gpu.getContext('webgl',{alpha:true,antialias:true,preserveDrawingBuffer:false})}catch{}
let program,U={},buffers=[],attr={};let cpuDepth;
function shader(kind,src){const s=gl.createShader(kind);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('shader');return s}
if(gl){try{
program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,`
attribute vec3 p,c;attribute float size;uniform vec3 camera,R,T,F;uniform vec2 screen;uniform float scale,persp,ratio,point,sweep;varying vec3 color;
void main(){vec3 v=p-camera;float d=dot(v,F);float k=mix(1.,d,persp);vec2 xy=vec2(dot(v,R),dot(v,T))*vec2(2.*scale/screen.x,2.*scale/screen.y);float z=persp>.5?(1.006*d-.105):((d-15.)/22.);gl_Position=vec4(xy,z,k);gl_PointSize=clamp(size*point*ratio*(persp>.5?1.7/max(.80,d):1.),1.,2.35*ratio);float band=(1.-smoothstep(0.,.24,abs(p.x-sweep)))*(1.-persp);color=c+vec3(.30,.28,.19)*band*step(.33,max(c.r,c.g));}`));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float;varying vec3 color;void main(){gl_FragColor=vec4(color,1.);}'));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('program');
gl.useProgram(program);for(const n of ['camera','R','T','F','screen','scale','persp','ratio','point','sweep'])U[n]=gl.getUniformLocation(program,n);for(const n of ['p','c','size'])attr[n]=gl.getAttribLocation(program,n);
for(const a of [solids,nearSolids,lines,nearLines,pts,nearPts]){const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a),gl.STATIC_DRAW);buffers.push([b,a.length/7])}
gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);
}catch{gl=null}}
function baseCamera(){const phi=.59+smX*.16+(reduced()?0:.075*(1-ease(Math.min(1,age/3700)))), elev=.54+smY*.075;
let R=[Math.cos(phi),0,-Math.sin(phi)],T=[-Math.sin(phi)*Math.sin(elev),Math.cos(elev),-Math.cos(phi)*Math.sin(elev)],F=[-Math.sin(phi)*Math.cos(elev),-Math.sin(elev),-Math.cos(phi)*Math.cos(elev)];return {R,T,F,C:sub([0,1.41,0],mul(F,15)),s:Math.min(w/12.40,h/8.56),persp:0}}
function pose(){let g=clamp(progress/.86,0,1),m=g*length,i=0;while(i<2&&m>segments[i]){m-=segments[i++]}
let pos=mix(route[i],route[i+1],clamp(m/segments[i],0,1)),d=sub(route[i+1],route[i]),yaw=Math.atan2(d[0],-d[2]);let turn=ease(clamp((progress-.86)/.14,0,1));yaw=yaw*(1-turn)+yawFlip*Math.PI*turn;
return {pos,yaw,turn,g};}
function robotCam(o){let a=o.yaw,pitch=-.09-o.turn*.31*(1-yawFlip),F=[Math.sin(a)*Math.cos(pitch),Math.sin(pitch),-Math.cos(a)*Math.cos(pitch)],R=[Math.cos(a),0,Math.sin(a)],T=[-Math.sin(a)*Math.sin(pitch),Math.cos(pitch),Math.cos(a)*Math.sin(pitch)];return {R,T,F,C:vadd(o.pos,[0,.78,0]),s:Math.min(w*.53,h*(.73-.28*o.turn)),persp:1}}
function proj(p,v){let d=sub(p,v.C),z=dot(d,v.F),k=v.persp?z:1;if(v.persp&&z<=.065)return null;return [w/2+dot(d,v.R)*v.s/k,h/2-dot(d,v.T)*v.s/k,z]}
function drawWorld(v){if(gl&&!gl.isContextLost()){gl.viewport(0,0,gpu.width,gpu.height);gl.clearColor(eye?.079:0,eye?.109:0,eye?.101:0,eye?1:0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
gl.uniform3fv(U.camera,v.C);gl.uniform3fv(U.F,v.F);gl.uniform3fv(U.R,v.R);gl.uniform3fv(U.T,v.T);gl.uniform2f(U.screen,w,h);gl.uniform1f(U.scale,v.s);gl.uniform1f(U.persp,v.persp);gl.uniform1f(U.ratio,dpr);gl.uniform1f(U.sweep,reduced()||age>=3600?-9:-4.4+8.8*age/3600);gl.uniform1f(U.point,clamp(w/510,1.0,1.95));
buffers.forEach(([b,n],i)=>{if(i%2===1&&!eye)return;gl.bindBuffer(gl.ARRAY_BUFFER,b);for(const [name,count,offset] of [['p',3,0],['c',3,12],['size',1,24]]){gl.enableVertexAttribArray(attr[name]);gl.vertexAttribPointer(attr[name],count,gl.FLOAT,false,28,offset)}
if(i<2){gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(2,2)}else gl.disable(gl.POLYGON_OFFSET_FILL);
gl.drawArrays(i<2?gl.TRIANGLES:i<4?gl.LINES:gl.POINTS,0,n)});
ctx.drawImage(gpu,0,0,w,h);
}else{
// CPU fallback retains the same geometry and viewpoint on devices without WebGL.
const cw=Math.round(w),ch=Math.round(h);if(!cw||!ch)return;
if(!cpuDepth||cpuDepth.width!==cw||cpuDepth.height!==ch){cpuDepth={width:cw,height:ch,img:new ImageData(cw,ch),z:new Float32Array(cw*ch),can:document.createElement('canvas')};cpuDepth.can.width=cw;cpuDepth.can.height=ch}
const {img,z,can}=cpuDepth,raw=new Uint32Array(img.data.buffer);raw.fill(eye?0xff1a1c14:0);z.fill(Infinity);
for(const a of eye?[pts,nearPts]:[pts]){for(let i=0;i<a.length;i+=7){const x=a[i]-v.C[0],y=a[i+1]-v.C[1],q=a[i+2]-v.C[2],D=x*v.F[0]+y*v.F[1]+q*v.F[2];if(v.persp&&D<.07)continue;const k=v.s/(v.persp?D:1),px=(cw*.5+(x*v.R[0]+y*v.R[1]+q*v.R[2])*k)|0,py=(ch*.5-(x*v.T[0]+y*v.T[1]+q*v.T[2])*k)|0;if(px<0||px>=cw||py<0||py>=ch)continue;const idx=py*cw+px;if(z[idx]<D)continue;z[idx]=D;raw[idx]=0xff000000|(clamp(a[i+5]*255,0,255)<<16)|(clamp(a[i+4]*255,0,255)<<8)|clamp(a[i+3]*255,0,255)}}
can.getContext('2d').putImageData(img,0,0);ctx.drawImage(can,0,0,w,h)}
}
function path2(p,col,width=1,dash=[]){if(p.length<2)return;ctx.beginPath();ctx.setLineDash(dash);ctx.lineWidth=width;ctx.lineJoin='round';ctx.lineCap='round';ctx.strokeStyle=col;let started=false;for(const pt of p){if(!pt){started=false;continue}if(started)ctx.lineTo(pt[0],pt[1]);else ctx.moveTo(pt[0],pt[1]);started=true}ctx.stroke();ctx.setLineDash([])}
function ring(x,y,r,col,fill=false){ctx.beginPath();ctx.arc(x,y,r,0,2*Math.PI);if(fill){ctx.fillStyle=col;ctx.fill()}else{ctx.strokeStyle=col;ctx.lineWidth=1.2;ctx.stroke()}}
function badge(x,y,txt){ctx.font='600 '+(w<440?11:12)+'px -apple-system, BlinkMacSystemFont, sans-serif';let bw=ctx.measureText(txt).width+18; x=clamp(x,3,w-bw-3);y=clamp(y,4,h-26);ctx.fillStyle='#18201dec';ctx.fillRect(x,y,bw,22);ctx.strokeStyle='#c787626e';ctx.lineWidth=1;ctx.strokeRect(x+.5,y+.5,bw-1,21);ctx.fillStyle='#ffac81';ctx.textBaseline='middle';ctx.fillText(txt,x+9,y+11)}
function mapMarks(v,o){let pp=p=>proj(vadd(p,[0,.028,0]),v),points=route.map(pp);
path2(points,'#f2ac86',1.5,[3,4]);let walked=[points[0]],rem=o.g*length;for(let i=0;i<3;i++){if(rem<segments[i])break;walked.push(points[i+1]);rem-=segments[i]}walked.push(pp(o.pos));path2(walked,'#ff9261',clamp(w/225,2,3.5));
let p=pp(o.pos),a=o.yaw;let triangle=[[0,.58],[-.21,-.23],[.21,-.23]].map(([side,forward])=>pp(vadd(o.pos,[forward*Math.sin(a)+side*Math.cos(a),.028,-forward*Math.cos(a)+side*Math.sin(a)])));
const cone=[p,...Array.from({length:15},(_,i)=>pp(vadd(o.pos,[Math.sin(a-.49+.98*i/14)*1.24,.015,-Math.cos(a-.49+.98*i/14)*1.24]))),p];ctx.beginPath();cone.forEach((k,i)=>i?ctx.lineTo(k[0],k[1]):ctx.moveTo(k[0],k[1]));ctx.fillStyle='#ffd5a936';ctx.fill();path2(cone,'#ffc79a80',.8);ctx.beginPath();triangle.forEach((k,i)=>i?ctx.lineTo(k[0],k[1]):ctx.moveTo(k[0],k[1]));ctx.closePath();ctx.fillStyle='#fff6dc';ctx.fill();ctx.strokeStyle='#b46948';ctx.stroke();
if(o.g>.04){ring(...points[0].slice(0,2),3.1,'#eac1a4',true)}
let top=proj([2.7,1.05,-2.5],v),q=proj(target,v);const s=clamp(w/70,5,11),ex=top[0]+s*2.2,ey=top[1]-s*2.8;
for(const [sx,sy] of [[1,1],[-1,1],[-1,-1],[1,-1]])path2([[q[0]+sx*s,q[1]+sy*s*.55],[q[0]+sx*s,q[1]+sy*s*1.18],[q[0]+sx*s*.45,q[1]+sy*s*1.18]],'#ff9e68',1.5);
path2([[top[0]+3,top[1]],[ex,ey],[ex+7,ey]],'#ffac7d',1);badge(ex+7,ey-11,'소화기');
}
function eyeMarks(v,o){const c='#dde5d8af',x=w/2,y=h/2;path2([[x-8,y],[x-3,y]],c);path2([[x+3,y],[x+8,y]],c);path2([[x,y-8],[x,y-3]],c);path2([[x,y+3],[x,y+8]],c);
if(o.g<.95)return;const corners=[];for(const xx of [2.50,2.90])for(const yy of [.025,.94])for(const zz of [-2.66,-2.34]){let pt=proj([xx,yy,zz],v);if(!pt)return;corners.push(pt)}
let x1=Math.max(7,Math.min(...corners.map(p=>p[0]))-4),x2=Math.min(w-7,Math.max(...corners.map(p=>p[0]))+4),y1=Math.max(8,Math.min(...corners.map(p=>p[1]))-4),y2=Math.min(h-8,Math.max(...corners.map(p=>p[1]))+4);if(x1>=x2||y1>=y2)return;
for(let [a,b,sx,sy] of [[x1,y1,1,1],[x2,y1,-1,1],[x1,y2,1,-1],[x2,y2,-1,-1]])path2([[a+sx*12,b],[a,b],[a,b+sy*12]],'#ffad80',2);badge(x1+4,y1+4,'소화기');
}
function draw(){let o=pose(),v=eye?robotCam(o):baseCamera();ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);drawWorld(v);eye?eyeMarks(v,o):mapMarks(v,o);if(eye&&progress>=1){const k=proj(target,v),seen=k&&k[0]>=0&&k[0]<=w&&k[1]>=0&&k[1]<=h;let text=seen?'시야 안':'시야 밖';if(by('verdict').textContent!==text)by('verdict').textContent=text}if(!rendered){host.classList.add('ready');rendered=true}}
const play=by('play'),pLabel=by('play-label'),slider=by('time'),aim=by('aim'),mapButton=by('map-mode'),eyeButton=by('eye-mode');
function ui(){let m=clamp(progress/.86,0,1);slider.value=Math.round(progress*1000);slider.style.setProperty('--pct',progress*100+'%');by('distance').value=(m*8.188).toFixed(2)+' / 8.19 m';let state=progress>=1?'정지':progress>=.86?'방향 정렬':progress>0?'이동 중':'출발';by('read-state').textContent=state;slider.setAttribute('aria-valuetext',state+', '+(m*8.188).toFixed(2)+'미터');let next=playing?'일시정지':progress>=1?'다시 재생':progress>0?'이어서 재생':'주행 재생';if(pLabel.textContent!==next){pLabel.textContent=next;play.querySelector('.play-glyph').textContent=playing?'Ⅱ':'▶'}mapButton.setAttribute('aria-pressed',!eye);eyeButton.setAttribute('aria-pressed',eye);aim.hidden=!(eye&&progress>=1);by('toward').setAttribute('aria-pressed',!reverse);by('away').setAttribute('aria-pressed',reverse);}
function tick(t){raf=0;if(!active||document.hidden)return;const dt=last?Math.min(60,t-last):16;last=t;age+=dt;const k=reduced()?1:1-Math.exp(-dt/136);smX+=(hoverX-smX)*k;smY+=(hoverY-smY)*k;yawFlip+=((reverse?1:0)-yawFlip)*(reduced()?1:1-Math.exp(-dt/105));if(playing){progress=Math.min(1,progress+dt/8800);if(progress>=1)playing=false;ui()}draw();if(playing||Math.abs(hoverX-smX)+Math.abs(hoverY-smY)>.004||Math.abs((reverse?1:0)-yawFlip)>.001||(!reduced()&&!eye&&age<3800))wake();else last=0}
function wake(){if(!raf&&active&&!document.hidden)raf=requestAnimationFrame(tick)}
function crossfade(){if(rendered&&!reduced()){host.querySelector('.previous')?.remove();let prev=document.createElement('canvas');prev.className='previous';prev.setAttribute('aria-hidden','true');prev.width=canvas.width;prev.height=canvas.height;prev.getContext('2d').drawImage(canvas,0,0);host.appendChild(prev);prev.animate([{opacity:1},{opacity:0}],{duration:240,easing:'ease-out'}).onfinish=()=>prev.remove()}}
function setMode(val){if(eye!==val)crossfade();eye=val;ui();if(w&&h)draw();wake()}
function setDir(val){if(val!==reverse)crossfade();reverse=val;yawFlip=val?1:0;ui();if(w&&h)draw();wake()}
mapButton.onclick=()=>setMode(false);eyeButton.onclick=()=>setMode(true);by('toward').onclick=()=>setDir(false);by('away').onclick=()=>setDir(true);
by('stop-view').onclick=()=>{playing=false;progress=1;reverse=false;yawFlip=0;setMode(true)};
play.onclick=()=>{if(!playing&&progress>=1){progress=0;reverse=false;yawFlip=0}playing=!playing;ui();wake()};
slider.oninput=()=>{playing=false;progress=+slider.value/1000;reverse=false;yawFlip=0;ui();wake()};
slider.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();slider.value=+slider.value+(['ArrowRight','ArrowUp'].includes(e.key)?20:-20);slider.oninput()});
host.addEventListener('pointermove',e=>{if(eye||coarse.matches||reduced()||e.pointerType==='touch')return;let r=host.getBoundingClientRect();hoverX=2*(e.clientX-r.left)/r.width-1;hoverY=1-2*(e.clientY-r.top)/r.height;wake()});
host.addEventListener('pointerleave',()=>{hoverX=hoverY=0;wake()});
function size(){let r=host.getBoundingClientRect();w=r.width;h=r.height;if(!w||!h)return;dpr=Math.min(2,devicePixelRatio||1);canvas.width=gpu.width=Math.round(w*dpr);canvas.height=gpu.height=Math.round(h*dpr);wake()}
new ResizeObserver(size).observe(host);new IntersectionObserver(([e])=>{active=e.isIntersecting;last=0;if(active)wake()}).observe(host);
document.addEventListener('visibilitychange',()=>{last=0;wake()});reduce.addEventListener('change',()=>{hoverX=hoverY=0;wake()});
size();ui();
})();
