// Observations are an RGB detector box and the robot pose. The sweep is shared
// across prompts and scenes. No target positions or viewpoints enter this policy.
export function searchPolicy(stations){
  let index=0,sweep=0,bearing=null,close=0,lost=0,arrived=false,detour=false;
  const norm=a=>Math.atan2(Math.sin(a),Math.cos(a));
  return ({x,z,yaw},boxes,blocked=false)=>{
    if(blocked&&!detour){detour=true;bearing=null;close=0;if(arrived){index++;arrived=false;sweep=0;}}
    const b=boxes.filter(b=>b.score>=.36).sort((a,b)=>b.score-a.score)[0];
    if(b&&!detour){
      const [left,,width,height]=b.box,cx=(left+width/2)/320;
      const angle=Math.atan((cx-.5)*2*Math.tan(68*Math.PI/360));bearing=yaw-angle;lost=0;
      close=Math.abs(cx-.5)<.13&&height/240>=.57?close+1:0;
      if(close>=3)return {type:'goal_stop'};
      if(Math.abs(angle)>.095)return {type:'turn',yaw:bearing};
      return close?{type:'observe'}:{type:'forward',metres:.22};
    }
    close=0;
    if(bearing!==null&&++lost<=2)return {type:'turn',yaw:bearing+(lost===1?.12:-.12)};
    bearing=null;
    if(index>=stations.length)return {type:'search_exhausted'};
    let [tx,tz]=stations[index];
    // Route through the shared doorway when crossing between rooms.
    if(x*tx<0&&Math.abs(z)>.12){tx=Math.sign(x)*Math.max(.6,Math.abs(x));tz=0;}
    const dist=Math.hypot(tx-x,tz-z);
    if(dist>.16&&!arrived){
      const to=Math.atan2(x-tx,z-tz);
      return Math.abs(norm(to-yaw))>.10?{type:'turn',yaw:to}:{type:'forward',metres:Math.min(.38,dist)};
    }
    arrived=true;detour=false;
    if(sweep<8)return {type:'turn',yaw:sweep++*Math.PI/4};
    sweep=0;index++;arrived=false;return {type:'observe'};
  };
}
