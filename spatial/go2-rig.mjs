import * as T from './three.mjs';
export async function go2Rig(){
  const loader=new T.GLTFLoader().setMeshoptDecoder(T.MeshoptDecoder);
  const gltf=await loader.loadAsync(new URL('go2.glb',import.meta.url).href);
  const body=new T.Group(),basis=new T.Group(),legs=[];
  basis.quaternion.setFromRotationMatrix(new T.Matrix4().set(0,-1,0,0,0,0,1,0,-1,0,0,0,0,0,0,1));
  basis.add(gltf.scene);body.add(basis);gltf.scene.getObjectByName('base').position.z=.305;
  for(const name of ['FL','FR','RL','RR']){
    const hip=gltf.scene.getObjectByName(name+'_thigh'),knee=gltf.scene.getObjectByName(name+'_calf');
    hip.rotation.y=.79;knee.rotation.y=-1.54;legs.push({hip,knee,phase:['FL','RR'].includes(name)?1:-1});
  }
  function gait(distance, moving){
    for(const {hip,knee,phase} of legs){
      const d=moving?.27*Math.sin(distance*19)*phase:0;
      hip.rotation.y=.79+d;knee.rotation.y=-1.54+Math.max(0,-d)*1.4;
    }
  }
  return {body,gait};
}
