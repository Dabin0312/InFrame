// Coordinates are metres. Positive z points toward the open side of the cutaway.
export const bounds = 3.65;
export const start = { x: -2.8, z: 2.7, yaw: 1.24 };
export const target = { x: 2.7, z: -2.5 };
export const observation = { x: 2.7, z: -2 };
export const obstacles = [
  { x: -.5, z: 0, width: 1.8, depth: 1.2 },
  { x: 1.3, z: .2, width: .8, depth: 1.3 },
  { ...target, width: .36, depth: .36 }
];
export const reference = [
  [start.x, 0, start.z], [1.9000002, .1999995, 1.0999992],
  [2.0000002, .1999995, .9499992], [observation.x, 0, observation.z]
];
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const distance = (a, b) => Math.hypot(a.x-b.x, a.z-b.z);
export const heading = (a, b) => Math.atan2(b.x-a.x, a.z-b.z);
export const angleDelta = (a, b) => Math.atan2(Math.sin(b-a), Math.cos(b-a));
const radius = .235;

export function canStand(x, z, clearance = radius) {
  if (Math.abs(x) > bounds || Math.abs(z) > bounds) return false;
  return obstacles.every(box => {
    const dx = Math.max(0, Math.abs(x-box.x)-box.width/2);
    const dz = Math.max(0, Math.abs(z-box.z)-box.depth/2);
    return Math.hypot(dx, dz) >= clearance - 1e-8;
  });
}

export function move(pose, dx, dz) {
  const before = { ...pose };
  const nextX = clamp(pose.x + dx, -bounds, bounds);
  const nextZ = clamp(pose.z + dz, -bounds, bounds);
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
    if (!canStand(a.x+(b.x-a.x)*ratio, a.z+(b.z-a.z)*ratio, radius + Math.min(.02, distance(a,b)*Math.min(ratio,1-ratio)*.3))) return false;
  }
  return true;
}

// Search the room on click. Shortcut only segments the robot's footprint can pass.
export function pathTo(from, to) {
  if (!canStand(to.x, to.z)) return [];
  if (clearSegment(from, to)) return [to];
  const size = 37, step = .2, offset = 3.6;
  const point = id => ({ x: (id % size)*step-offset, z: Math.floor(id/size)*step-offset });
  const gridId = (x,z) => x + z*size;
  const coords = v => clamp(Math.round((v+offset)/step), 0, size-1);
  const first = gridId(coords(from.x), coords(from.z));
  const paths = new Map();
  const queue = [];
  // Start from a reachable grid centre, including poses close to an obstacle edge.
  for (let z=-1; z<=1; z++) for (let x=-1; x<=1; x++) {
    const gx = first % size+x, gz = Math.floor(first/size)+z;
    if (gx<0 || gx>=size || gz<0 || gz>=size) continue;
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
      if (x<0 || x>=size || z<0 || z>=size) continue;
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
    if (obstacles.slice(0,2).some(b=>Math.abs(x-b.x)<b.width/2 && Math.abs(z-b.z)<b.depth/2)) return false;
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
  yaw+=angleDelta(yaw,backward?Math.PI:0)*turn;
  return { x:a[0]+(b[0]-a[0])*t, z:a[2]+(b[2]-a[2])*t, yaw };
}
