class ComparisonMap {
  constructor(canvas, pins, floor, onPick) {
    this.canvas = canvas;
    this.pins = pins;
    this.floor = floor;
    this.onPick = onPick;
    this.mode = 'room';
    this.cases = window.InFrame.cases.filter(c => c.group === 'shared');
    this.colors = ['#73ddce','#ffb46c','#d4a9ff'];
    this.pinKey = '';
    this.observer = new ResizeObserver(() => this.redraw());
    this.observer.observe(canvas);
  }
  update(current, traces, tick, mode, selected, probe) {
    Object.assign(this,{current,traces,tick,mode,selected,probe});
    this.redraw();
  }
  redraw() {
    if (!this.traces) return;
    const {canvas, floor, current, mode, tick} = this;
    const ctx = canvas.getContext('2d');
    const width=canvas.clientWidth, height=canvas.clientHeight;
    if (!width || !height) return;
    const dpr=Math.min(2, window.devicePixelRatio || 1);
    if (canvas.width !== Math.round(width*dpr) || canvas.height !== Math.round(height*dpr)) {
      canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    }
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.fillStyle='#152d2a';ctx.fillRect(0,0,width,height);
    let scope=floor.vertices, minSpan=1;
    if (mode==='event' && current.group==='shared') {
      const focus=current.diagnoses[this.selected] || current.diagnoses[2];
      const p=focus.xyz;
      scope=[[p[0]-.76,p[2]-.76],[p[0]+.76,p[2]+.76]];
    }
    const xs=scope.map(p=>p[0]),zs=scope.map(p=>p[1]);
    let xmin=Math.min(...xs),xmax=Math.max(...xs),zmin=Math.min(...zs),zmax=Math.max(...zs);
    const padding=mode==='atlas'?28:15;
    const s=Math.min((width-2*padding)/Math.max(minSpan,xmax-xmin),(height-2*padding)/Math.max(minSpan,zmax-zmin));
    const ox=width/2-(xmin+xmax)/2*s, oz=height/2-(zmin+zmax)/2*s;
    const xy = p => [p[0]*s+ox,p[1]*s+oz];
    function path(points,color,lineWidth,dash=[]) {
      if (!points.length) return;
      ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.setLineDash(dash);
      for (let i=0;i<points.length;i++) {const [x,y]=xy(points[i]);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);}
      ctx.stroke();ctx.setLineDash([]);
    }
    // Render the floor at the current scale with no atlas resampling.
    ctx.fillStyle='#3b5952';ctx.beginPath();
    for (const face of floor.triangles) {
      const a=xy(floor.vertices[face[0]]),b=xy(floor.vertices[face[1]]),c=xy(floor.vertices[face[2]]);
      ctx.moveTo(...a);ctx.lineTo(...b);ctx.lineTo(...c);ctx.closePath();
    }
    ctx.fill();
    const spacing=mode==='event'?.25:2;
    ctx.lineWidth=.5;ctx.strokeStyle='#c0d1b819';ctx.beginPath();
    for(let x=Math.ceil(-ox/s/spacing)*spacing;x<(width-ox)/s;x+=spacing){ctx.moveTo(x*s+ox,0);ctx.lineTo(x*s+ox,height);}
    for(let z=Math.ceil(-oz/s/spacing)*spacing;z<(height-oz)/s;z+=spacing){ctx.moveTo(0,z*s+oz);ctx.lineTo(width,z*s+oz);}
    ctx.stroke();
    const ring=(at,r,color)=>{ctx.beginPath();ctx.arc(...xy(at),r,0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=1.3;ctx.stroke()};
    for(const v of floor.views) ring(v,3,'#e6eee2');
    const [gx,gy]=xy(floor.target);ctx.fillStyle='#ff9c73';ctx.beginPath();ctx.moveTo(gx,gy-5);ctx.lineTo(gx+5,gy);ctx.lineTo(gx,gy+5);ctx.lineTo(gx-5,gy);ctx.fill();ctx.font='bold 11px system-ui';ctx.fillText('C',gx+6,gy-4);
    if(mode==='atlas'){
      this.drawPins(ctx,xy,width,height);
    }else{
      this.pinKey='';if(this.pins.children.length)this.pins.replaceChildren();
      const colors=this.colors;
      path(this.traces[0], '#9bbeb88c',1,[3,4]);
      this.traces.forEach((track,i)=>{
        const n=Math.min(tick,track.length-1);
        path(track.slice(0,n+1),colors[i],i===0?3.3:2,i===1?[5,2]:[]);
      });
      if(current.group==='shared'){
        [1,2].forEach(i=>{
          const d=current.diagnoses[i],c=colors[i];
          const events=d.contacts.length?d.contacts.map(a=>a.xz):[[d.xyz[0],d.xyz[2]]];
          for(const at of events){
            const [x,y]=xy(at),r=i===1?5:3.6;ctx.lineWidth=1.7;ctx.strokeStyle=c;
            ctx.beginPath();ctx.moveTo(x-r,y-r);ctx.lineTo(x+r,y+r);ctx.moveTo(x+r,y-r);ctx.lineTo(x-r,y+r);ctx.stroke();
          }
        });
      }
      const [bx,bz]=xy(current.start);ctx.strokeStyle='#ffffea';ctx.lineWidth=1.5;ctx.strokeRect(bx-4,bz-4,8,8);
      this.traces.forEach((track,i)=>{
        const v=track[Math.min(tick,track.length-1)], [x,z]=xy(v);ctx.save();ctx.translate(x,z);ctx.rotate(-v[2]);
        // Coincident poses each retain a differently sized outline.
        const a=9-i*1.7;ctx.beginPath();ctx.moveTo(0,-a);ctx.lineTo(-a*.56,a*.58);ctx.lineTo(a*.56,a*.58);ctx.closePath();ctx.strokeStyle=colors[i];ctx.lineWidth=1.9;ctx.stroke();ctx.restore();
      });
      if(this.probe && current.group==='shared'){
        const diag=current.diagnoses[this.selected],begin=[diag.xyz[0],diag.xyz[2]],end=diag.probe.alternative.end_xz;
        path([begin,end],'#e3ff91',2.5,[3,2]);ring(end,3,'#e3ff91');
      }
    }
    const length=mode==='event'?.25:2,bar=length*s;
    ctx.fillStyle='#0a211bd9';ctx.fillRect(4,height-22,Math.max(32,bar+15),19);
    ctx.strokeStyle='#e5eee5';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(8,height-9);ctx.lineTo(8+bar,height-9);ctx.stroke();
    ctx.font='9px system-ui';ctx.fillStyle='#f1f3e7';ctx.fillText(mode==='event'?'25 cm':'2 m',8,height-12);
  }
  drawPins(ctx,xy,width,height){
    const key=[this.current.id,width,height].join('/');
    const placed=[];
    const nodes=[];
    for(const c of this.cases){
      const start=xy(c.start);
      const incidents=c.diagnoses.slice(1).map(d=>xy([d.xyz[0],d.xyz[2]]));
      const x=(incidents[0][0]+incidents[1][0])/2,z=(incidents[0][1]+incidents[1][1])/2;
      ctx.strokeStyle='#e5efe4';ctx.lineWidth=1;ctx.strokeRect(start[0]-2,start[1]-2,4,4);
      for (let i=0;i<incidents.length;i++) {
        const end=incidents[i],r=4-i;ctx.strokeStyle=this.colors[i+1];
        ctx.beginPath();ctx.moveTo(...start);ctx.lineTo(...end);ctx.stroke();
        ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(end[0]-r,end[1]-r);ctx.lineTo(end[0]+r,end[1]+r);
        ctx.moveTo(end[0]+r,end[1]-r);ctx.lineTo(end[0]-r,end[1]+r);ctx.stroke();
      }
      let best=null;
      for(const r of [12,28,44,60,76,92])for(const angle of [-.6,.6,-1.5,1.5,2.4,-2.4,0,Math.PI]){
        const px=Math.max(16,Math.min(width-16,x+r*Math.cos(angle))),pz=Math.max(11,Math.min(height-12,z+r*Math.sin(angle)));
        const overlap=placed.reduce((n,p)=>n+(Math.abs(px-p[0])<30&&Math.abs(pz-p[1])<17?1:0),0);
        const score=overlap*500+Math.hypot(x-px,z-pz);
        if(!best||score<best.score)best={px,pz,score};
      }
      placed.push([best.px,best.pz]);
      ctx.strokeStyle=c.id===this.current.id?'#ffd5a4':'#c9bd9f';ctx.lineWidth=1;
      ctx.beginPath();ctx.moveTo(x,z);ctx.lineTo(best.px,best.pz);ctx.stroke();

      if(this.pinKey!==key){
        const b=document.createElement('button');b.className='map-pin';b.textContent=c.id.slice(-3);b.title=c.id+' 주행 보기';
        b.setAttribute('aria-label',b.title);b.setAttribute('aria-current',String(c.id===this.current.id));
        b.style.left=best.px+'px';b.style.top=best.pz+'px';b.onclick=()=>this.onPick(c.id);nodes.push(b);
      }
    }
    if(this.pinKey!==key){this.pins.replaceChildren(...nodes);this.pinKey=key}
  }
}
