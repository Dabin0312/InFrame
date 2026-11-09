import {resolveGoal} from './prompt.mjs';
const $=id=>document.getElementById(id),floor=$('floor').getContext('2d'),eye=$('eye').getContext('2d');
const url=new URL('../evidence/free-search.json',import.meta.url);
let rows=[],selected=null,busy=false,revision=0,triangles=[];
const point=([x,z])=>selected?.environment==='castle'?[320+(x-2.25)*78,240+(z-9.5)*78]:[320+x*68,240+z*68];
function drawTrace(path){
  floor.fillStyle='#f2f5f0';floor.fillRect(0,0,640,480);
  const line=(a,b,color,width)=>{floor.beginPath();floor.moveTo(...point(a));floor.lineTo(...point(b));floor.strokeStyle=color;floor.lineWidth=width;floor.stroke();};
  if(selected?.environment==='castle'){
    const [x,y]=point([0,7]),[xx,yy]=point([4.5,12]);
    floor.save();floor.beginPath();floor.rect(x,y,xx-x,yy-y);floor.clip();floor.fillStyle='#c9ded1';
    for(const tri of triangles){floor.beginPath();tri.forEach(([tx,,tz],i)=>floor[i?'lineTo':'moveTo'](...point([tx,tz])));floor.closePath();floor.fill();}
    floor.restore();floor.strokeStyle='#798e85';floor.lineWidth=2;floor.strokeRect(x,y,xx-x,yy-y);
  }else for(const [a,b] of [[[-4,-3],[4,-3]],[[4,-3],[4,3]],[[4,3],[-4,3]],[[-4,3],[-4,-3]],[[0,-3],[0,-.95]],[[0,.95],[0,3]]])line(a,b,'#6d7c76',5);
  for(let i=1;i<path.length;i++)line(path[i-1],path[i],'#14867a',3.5);
  if(!path.length)return;
  for(const [p,fill] of [[path[0],'white'],[path.at(-1),'#19433e']]){floor.beginPath();floor.arc(...point(p),6,0,Math.PI*2);floor.fillStyle=fill;floor.fill();floor.strokeStyle='#19433e';floor.lineWidth=2;floor.stroke();}
}
function resetControls(on){busy=on;for(const id of ['layout','condition','object','run'])$(id).disabled=on;}
function describe(r,recorded){
  const end={goal_stop:'紐⑺몴 STOP',search_exhausted:'�먯깋 �꾨즺 쨌 紐⑺몴 STOP �놁쓬',budget_exhausted:'�ㅽ뀦 �쒕룄 �꾨떖 쨌 紐⑺몴 STOP �놁쓬'}[r.end];
  $('photo-label').textContent=r.end==='goal_stop'?'泥� STOP 쨌 濡쒕큸 RGB':'留덉�留� 愿�痢� 쨌 濡쒕큸 RGB';
  $('audit').textContent=(recorded?'���λ맂 二쇳뻾':'諛⑷툑 �ㅽ뻾�� 二쇳뻾')+' 쨌 '+r.prompt+' 쨌 '+end+' 쨌 '+r.trace.length+' �ㅽ뀦'+
    (r.end==='goal_stop'?' 쨌 '+(r.matched?'愿묒꽑�� 援먰넻 肄섏뿉 �우쓬':'援먰넻 肄� �쇱튂 �놁쓬')+(r.distance!=null?' 쨌 肄섍퉴吏� '+r.distance.toFixed(2)+' m':''):'');
}
async function show(){
  const version=++revision;
  selected=rows.find(r=>r.layout===+$('layout').value&&r.condition===$('condition').value);
  $('object').value=selected.prompt;drawTrace(selected.trace.map(s=>[s.x,s.z]));describe(selected,true);
  const im=new Image();im.src=selected.photo;await im.decode();if(version===revision)eye.drawImage(im,0,0);
}
$('layout').onchange=$('condition').onchange=show;
$('run').onclick=async()=>{
  if(busy||!selected)return;resetControls(true);revision++;$('audit').textContent='紐⑤뜽 以�鍮� 以묅��';
  try{
    const {prompt}=await resolveGoal($('object').value),{runSearch}=await import('./search-bench.mjs');const path=[];
    const r=await runSearch({prompt,start:selected.start,placement:selected.placement,environment:selected.environment},(frame,p,a,n)=>{
      eye.drawImage(frame,0,0);path.push([p.x,p.z]);drawTrace(path);
      $('photo-label').textContent='濡쒕큸 RGB';$('audit').textContent=prompt+' 쨌 �먯깋 以� 쨌 '+(n+1)+' �ㅽ뀦';
    });
    describe(r,false);const im=new Image();im.src=r.photo;await im.decode();eye.drawImage(im,0,0);
  }catch(e){$('audit').textContent=e.message;}finally{resetControls(false);}
};
try{
  const response=await fetch(url);if(!response.ok)throw Error('二쇳뻾 湲곕줉�� 遺덈윭�ㅼ� 紐삵뻽�댁슂.');
  rows=(await response.json()).runs;
  triangles=(await (await fetch(new URL('floor.json',import.meta.url))).json()).tris;
  for(const i of new Set(rows.map(r=>r.layout))){const r=rows.find(r=>r.layout===i);$('layout').add(new Option((r.environment==='castle'?'Castle �ㅼ틪 쨌 ':'�� 諛� 쨌 ')+(r.sceneLayout??i+1),String(i)));}
  const requested=Number(new URLSearchParams(location.search).get('layout'));if(rows.some(r=>r.layout===requested))$('layout').value=String(requested);
  await show();
}catch(e){$('audit').textContent=e.message;}
