// Reconstruct the independently seeded training cameras. Poses are used only for supervision.
import fs from 'node:fs';
import {peripheralSamples} from './peripheral-samples.mjs';
import {floorHeight} from '../spatial/navmesh.mjs';
const root=new URL('../spatial/floor.json',import.meta.url);
const {tris}=JSON.parse(fs.readFileSync(root));
const elevation=(x,z)=>floorHeight(tris,x,z);
const dist=JSON.parse(fs.readFileSync(process.argv[2]+'/distances.json'));
const poses=[];
for(const {i,p,anchors,distance,removed} of peripheralSamples(elevation,dist.length)){
  if(Math.abs(dist[i]-distance)>1e-5)throw Error('Mismatched camera sequence');
  poses.push({...p,anchors,removed});
}
fs.writeFileSync(process.argv[2]+'/poses.json',JSON.stringify(poses));
