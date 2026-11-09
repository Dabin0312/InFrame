import {floorHeight} from './navmesh.mjs';

const ns = 'http://www.w3.org/2000/svg';
function shape(tag, attributes) {
  const node = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

export function startMap(svg, floor, onPick, onInvalid) {
  const vertices = floor.tris.flat();
  const xs = vertices.map(p => p[0]), zs = vertices.map(p => p[2]);
  const x0 = Math.min(...xs) - 1, z0 = Math.min(...zs) - 1;
  const width = Math.max(...xs) + 1 - x0, height = Math.max(...zs) + 1 - z0;
  svg.setAttribute('viewBox', [x0, z0, width, height].join(' '));
  const paths = floor.tris.map(tri => 'M' + tri.map(([x,,z]) => x + ',' + z).join('L') + 'Z');
  svg.append(shape('path', {d:paths.join(''), fill:'#b7d8cf', stroke:'#b7d8cf', 'stroke-width':.035}));
  const [gx,,gz] = floor.target;
  svg.append(shape('circle', {cx:gx, cy:gz, r:.37, fill:'#bb5232', stroke:'white', 'stroke-width':.12}));
  const label = shape('text', {x:gx+.55, y:gz+.24, fill:'#913d22', 'font-size':.85, 'font-weight':700});
  label.textContent = 'C'; svg.append(label);
  const start = shape('circle', {r:.32, fill:'white', stroke:'#126e64', 'stroke-width':.14});
  const robot = shape('path', {d:'M0,-.58 L.37,.38 L0,.18 L-.37,.38 Z', fill:'#084b48', stroke:'white', 'stroke-width':.08});
  svg.append(start, robot);
  let cursor;
  function pose(x,z,yaw) {
    robot.setAttribute('transform','translate('+x+' '+z+') rotate('+(-yaw*180/Math.PI)+')');
  }
  function select(s) {
    const [x,,z] = s.xyz;
    start.setAttribute('cx',x); start.setAttribute('cy',z);
    cursor = [x,z]; pose(x,z,s.yaw);
  }
  function pick(x,z) {
    const y = floorHeight(floor.tris,x,z);
    if (y === null) { onInvalid(); return; }
    onPick([x,y,z]);
  }
  svg.addEventListener('click', event => {
    const p = new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    pick(p.x,p.y);
  });
  // Arrow keys move the selection in world units, independent of screen size.
  svg.addEventListener('keydown', event => {
    const step = event.shiftKey ? 1 : .25;
    const deltas = {ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]};
    const delta = deltas[event.key]; if (!delta) return;
    event.preventDefault(); pick(cursor[0]+delta[0],cursor[1]+delta[1]);
  });
  return {select, pose};
}
