// Measure the rendered GLB soles, then replay the live navigator on the same floor.
const fs=require('node:fs');
const {chromium}=require('playwright-core');
async function main(){
  const [origin, output]=process.argv.slice(2);
  const browser=await chromium.launch({channel:'chrome',args:process.platform==='darwin'?['--use-angle=metal']:[]});
  try{
    const page=await browser.newPage();await page.goto(origin+'/spatial/floor.json');
    const r=await page.evaluate(async()=>{
      const {go2Rig}=await import('/spatial/go2-rig.mjs');
      const {footprint,footRadius}=await import('/spatial/footprint.mjs');
      const {buildPlanner,followRoute}=await import('/spatial/route-planner.mjs');
      const {floorHeight,directFloorLength}=await import('/spatial/navmesh.mjs');
      const {registeredGoals}=await import('/spatial/goals.mjs');
      const T=await import('/spatial/three.mjs');
      const floor=await (await fetch('/spatial/floor.json')).json();
      const surface=footprint(floor),rig=await go2Rig(),v=new T.Vector3();
      const soles=['FL','FR','RL','RR'].map(name=>{
        const meshes=rig.body.getObjectByName(name+'_calf').children.filter(o=>o.position.z<-.20);
        if(meshes.length!==2)throw Error('Unexpected Go2 sole geometry');
        return {name,meshes};
      });
      function inspect(testFloor=false){
        rig.body.updateMatrixWorld(true);let reach=0;const outside=new Set();
        for(const {name,meshes} of soles)for(const mesh of meshes){
          const pos=mesh.geometry.attributes.position;
          for(let i=0;i<pos.count;i++){
            v.fromBufferAttribute(pos,i).applyMatrix4(mesh.matrixWorld);
            reach=Math.max(reach,Math.hypot(v.x-rig.body.position.x,v.z-rig.body.position.z));
            if(testFloor&&!outside.has(name)&&floorHeight(floor.tris,v.x,v.z)===null)outside.add(name);
          }
        }
        return {reach,outside:[...outside]};
      }
      let maxReach=0;
      for(let i=0;i<128;i++){rig.gait(i*2*Math.PI/128/19,true);maxReach=Math.max(maxReach,inspect().reach);}
      const start=floor.starts[0], goal=registeredGoals(floor).extinguisher;
      // Old point-centre planner selected these two original Castle waypoints for FRESH-015.
      const oldPath=[[4.5,.0348999984562397,13.25],goal.views[0]];
      const path=buildPlanner(floor)(start.xyz,goal.views);
      function drive(path, old){
        const p=[...start.xyz];let yaw=start.yaw,travel=0,at8,min=Infinity,steps=0,blocked=0;
        const poses=[];
        for(;steps<240;steps++){
          const action=old?legacyAction():followRoute(path,p,yaw,goal,true);
          if(action[2])break;
          const [f,r]=action;
          for(let j=0;j<4;j++){
            const mid=yaw+r*.03125;yaw+=r*.0625;
            const x=p[0]-Math.sin(mid)*f*.0625,z=p[2]-Math.cos(mid)*f*.0625;
            const next=[x,floorHeight(floor.tris,x,z),z];
            if(next[1]===null||!isFinite(directFloorLength(floor.tris,p,next))||(!old&&!surface.clear(p,next))){blocked++;continue;}
            p.splice(0,3,...next);travel+=f*.0625;
            min=Math.min(min,surface.clearance(x,z));
          }
          poses.push([...p]);rig.body.position.fromArray(p);rig.body.rotation.y=yaw;rig.gait(travel,f>0);
          if(steps===31)at8={p:[...p],yaw,travel,clearance:surface.clearance(p[0],p[2]),...inspect(true)};
        }
        function legacyAction(){
          const dist=v=>Math.hypot(p[0]-v[0],p[2]-v[2]);
          while(path.length>1&&dist(path[0])<.15)path.shift();
          const d=dist(path[0]),near=path.length===1&&d<.18,q=near?goal.xyz:path[0];
          const delta=Math.atan2(p[0]-q[0],p[2]-q[2])-yaw,turn=Math.atan2(Math.sin(delta),Math.cos(delta));
          return [near||Math.abs(turn)>.50?0:Math.min(.65,d*2),Math.max(-1.6,Math.min(1.6,turn*3)),near&&Math.abs(turn)<.18];
        }
        return {at8,min,steps,blocked,poses,reached:steps<240};
      }
      return {footRadius,maxReach,before:drive(oldPath,true),after:drive(path,false)};
    });
    fs.writeFileSync(output,JSON.stringify(r));
    console.log(JSON.stringify({maxReach:r.maxReach,before:r.before.at8,after:r.after.at8,min:r.after.min,blocked:r.after.blocked,reached:r.after.reached}));
    if(r.maxReach>=r.footRadius||r.after.min<r.footRadius||r.after.at8.outside.length||!r.after.reached)throw Error('Footprint verification failed');
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1});
