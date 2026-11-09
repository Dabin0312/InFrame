import * as T from './three.mjs';
export async function addIndoorGoals(world,overview,registry){
  await Promise.all(Object.entries(registry).filter(([,g])=>g.mesh).map(async([key,g])=>{
    const loader=new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder);
    const {scene}=await loader.loadAsync(new URL(g.mesh,import.meta.url).href);
    scene.traverse(node=>{
      if(!node.isMesh)return;
      node.material=new T.MeshBasicMaterial({map:node.material.map,color:node.material.color,side:T.DoubleSide});
      node.userData.goal=key;
    });
    const group=new T.Group();group.add(scene);
    group.rotation.y=g.yaw;
    const bounds=new T.Box3().setFromObject(group);
    group.scale.setScalar(g.height/(bounds.max.y-bounds.min.y));
    bounds.setFromObject(group);const c=bounds.getCenter(new T.Vector3());
    group.position.set(g.xyz[0]-c.x,g.xyz[1]-bounds.min.y,g.xyz[2]-c.z);
    world.add(group);overview.add(group.clone(true));
    const footprint=new T.Mesh(new T.CircleGeometry(g.radius,48),new T.MeshBasicMaterial({color:0xe9edef,side:T.DoubleSide}));
    footprint.rotation.x=-Math.PI/2;footprint.position.set(g.xyz[0],g.xyz[1]+.008,g.xyz[2]);overview.add(footprint);
  }));
}
