import {episode} from './episode.js';
const route=episode.route;
export const start={x:route[0][0],z:route[0][1],yaw:Math.atan2(route[1][0]-route[0][0],route[0][1]-route[1][1])};
export const target={x:episode.target[0],z:episode.target[2]};
export const observation={x:route.at(-1)[0],z:route.at(-1)[1]};
export const reference=route.map(([x,z])=>[x,0,z]);
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const distance = (a, b) => Math.hypot(a.x-b.x, a.z-b.z);
export const heading = (a, b) => Math.atan2(b.x-a.x, a.z-b.z);
export const angleDelta = (a, b) => Math.atan2(Math.sin(b-a), Math.cos(b-a));
const {rows,origin,resolution}=episode;
function cell(x,z){
  return [Math.floor((x-origin[0])/resolution),Math.floor((z-origin[1])/resolution)];
}
function at(x,z){const [i,j]=cell(x,z);return rows[j]?.[i]}
export function canStand(x,z){return at(x,z)==='.'}
export function move(pose, dx, dz) {
  const before = { ...pose };
  const nextX = pose.x + dx;
  const nextZ = pose.z + dz;
  if (canStand(nextX, nextZ)) {
    pose.x = nextX;
    pose.z = nextZ;
    return distance(before, pose);
  }
  if (canStand(nextX, pose.z)) pose.x = nextX;
  if (canStand(pose.x, nextZ)) pose.z = nextZ;
  return distance(before, pose);
}

function clearSegment(a, b) {
  const steps = Math.max(1, Math.ceil(distance(a,b)/.025));
  for (let i = 1; i <= steps; i++) {
    const ratio = i / steps;
    if (!canStand(a.x+(b.x-a.x)*ratio, a.z+(b.z-a.z)*ratio)) return false;
  }
  return true;
}

// Search the room on click. Shortcut only segments the robot's footprint can pass.
export function pathTo(from, to) {
  if (!canStand(to.x, to.z)) return [];
  if (clearSegment(from, to)) return [to];
  const size=rows[0].length, height=rows.length;
  const point=id=>({x:origin[0]+(id%size+.5)*resolution,z:origin[1]+(Math.floor(id/size)+.5)*resolution});
  const gridId=(x,z)=>x+z*size;
  const [sx,sz]=cell(from.x,from.z);
  const first=gridId(sx,sz);
  const paths = new Map();
  const queue = [];
  // Start from a reachable grid centre, including poses close to an obstacle edge.
  for (let z=-1; z<=1; z++) for (let x=-1; x<=1; x++) {
    const gx = first % size+x, gz = Math.floor(first/size)+z;
    if (gx<0 || gx>=size || gz<0 || gz>=height) continue;
    const id=gridId(gx,gz);
    if (clearSegment(from, point(id))) { paths.set(id,-1); queue.push(id); }
  }
  for (let head=0; head<queue.length; head++) {
    const id=queue[head], here=point(id);
    if (distance(here,to)<.36 && clearSegment(here,to)) {
      const raw=[to];
      for (let at=id; at!==-1; at=paths.get(at)) raw.push(point(at));
      raw.push(from); raw.reverse();
      const compact=[];
      for (let i=0; i<raw.length-1;) {
        let j=raw.length-1;
        while (j>i+1 && !clearSegment(raw[i],raw[j])) j--;
        compact.push(raw[j]); i=j;
      }
      return compact;
    }
    for (const [ox,oz] of [[0,-1],[1,0],[0,1],[-1,0],[1,-1],[1,1],[-1,1],[-1,-1]]) {
      const x=id%size+ox, z=Math.floor(id/size)+oz;
      if (x<0 || x>=size || z<0 || z>=height) continue;
      const next=gridId(x,z);
      if (paths.has(next) || !clearSegment(here,point(next))) continue;
      paths.set(next,id); queue.push(next);
    }
  }
  return [];
}

export function seesTarget(pose, horizontalFov, verticalFov, pitch) {
  const dist = distance(pose, target);
  if (Math.abs(angleDelta(pose.yaw, heading(pose,target))) > horizontalFov/2) return false;
  if (Math.abs(Math.atan2(.50-.78, dist)-pitch) > verticalFov/2) return false;
  const steps = Math.ceil(dist/.04);
  for (let i=1; i<steps; i++) {
    const x=pose.x+(target.x-pose.x)*i/steps, z=pose.z+(target.z-pose.z)*i/steps;
    if (distance({x,z},target)>.30 && at(x,z)==='#') return false;
  }
  return true;
}

const lengths = reference.slice(1).map((b,i)=>Math.hypot(...b.map((v,k)=>v-reference[i][k])));
export const pathLength=lengths.reduce((a,b)=>a+b,0);
export function sampleReference(progress, backward=false) {
  let remaining=clamp(progress/.86,0,1)*pathLength, index=0;
  while (index<lengths.length-1 && remaining>lengths[index]) remaining-=lengths[index++];
  const a=reference[index], b=reference[index+1], t=remaining/lengths[index];
  let yaw=Math.atan2(b[0]-a[0],a[2]-b[2]);
  const raw=clamp((progress-.86)/.14,0,1), turn=raw*raw*(3-2*raw);
  yaw+=angleDelta(yaw,backward?(heading(observation,target)+Math.PI):heading(observation,target))*turn;
  return { x:a[0]+(b[0]-a[0])*t, z:a[2]+(b[2]-a[2])*t, yaw };
}
