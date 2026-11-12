import {castle,prompts} from './castle.mjs';
import {footprint,footRadius} from '../spatial/footprint.mjs';
import {directFloorLength} from '../spatial/navmesh.mjs';

export const period=.25;
export const forwardLimit=.4;
export const yawLimit=1;
export function cappedAction(action){
  const twists=[[.22/period,0,0],[0,Math.PI/12/period,0],[0,-Math.PI/12/period,0],[0,0,1]];
  const [forward,yaw,stop]=twists[action];
  return [Math.min(forward,forwardLimit),Math.max(-yawLimit,Math.min(yaw,yawLimit)),stop];
}

export function placements(sim,anchors,removed){
  return anchors.flatMap((xz,k)=>k===removed?[]:[{xz,radius:sim.objectRadii[k]}]);
}

export function integrate(pose,twist,surface,sim){
  const [v,vy,w]=twist;
  if(!twist.every(Number.isFinite)||vy!==0||v<0||v>forwardLimit||Math.abs(w)>yawLimit)throw Error('Invalid Go2 command');
  const dt=period/4;
  let distance=0,blocked=false;
  for(let i=0;i<4;i++){
    const turn=w*dt,mid=pose.yaw+turn/2;
    pose.yaw+=turn;
    if(!v)continue;
    const x=pose.x-Math.sin(mid)*v*dt,z=pose.z-Math.cos(mid)*v*dt;
    const a=[pose.x,sim.elevation(pose.x,pose.z),pose.z],b=[x,sim.elevation(x,z),z];
    if(b[1]===null||!surface.clear(a,b)||!Number.isFinite(directFloorLength(sim.floor.tris,a,b))){
      blocked=true;continue;
    }
    distance+=Math.hypot(x-pose.x,z-pose.z);pose.x=x;pose.z=z;
  }
  return {distance,blocked};
}

export async function setup(){
  const sim=await castle(160,120);
  async function run({layout,goal,removed,limit}){
    const pose={...layout.start},surface=footprint(sim.floor,placements(sim,layout.anchors,removed));
    if(!surface.fits(pose.x,pose.z))throw Error('Invalid starting footprint');
    sim.place(layout.anchors,removed);
    const steps=[];
    let traveled=0,blocked=0,stopped=false;
    for(let i=0;i<limit;i++){
      sim.render(pose);
      // The separate policy process receives only the newly rendered camera bytes.
      const cmd=await window.decide(sim.ctx.canvas.toDataURL('image/png').split(',')[1]);
      const before={...pose};
      const motion=integrate(pose,cmd.sent,surface,sim);
      if(motion.blocked)blocked++;
      traveled+=motion.distance;
      steps.push({i:i+1,before,after:{...pose},...cmd,...motion});
      if(cmd.action===3){stopped=true;break;}
    }
    sim.render(pose);
    const photo=sim.ctx.canvas.toDataURL('image/png');
    const audit=sim.score(pose,goal); // Uses instance IDs only after the policy episode.
    if(removed===goal && audit.visible[goal].pixels!==0)throw Error('Removed mesh in depth-tested mask');
    const end=stopped?(removed===goal?'false_stop':audit.success?'success':'invalid_stop'):'step_limit';
    return {layout:layout.id,prompt:prompts[goal],goal,removed,start:layout.start,anchors:layout.anchors,
      steps,traveled,blocked,stopped,stopStep:stopped?steps.length:null,end,audit,photo,endpoint:pose,
      minCenterClearance:Math.min(...steps.map(s=>surface.clearance(s.after.x,s.after.z))),footRadius};
  }
  return {sim,run};
}
