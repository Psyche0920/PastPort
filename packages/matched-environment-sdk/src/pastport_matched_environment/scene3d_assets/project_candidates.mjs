/** Offline form of the viewer's candidate ray projection; never approves identities. */
import * as THREE from './three.module.js';
import {GLTFLoader} from './GLTFLoader.js';
import {readFile} from 'node:fs/promises';
let text='';for await(const chunk of process.stdin){text+=chunk;if(text.length>1024*1024)throw Error('projection input limit');}
const input=JSON.parse(text);if(!Array.isArray(input.nodes)||input.nodes.length>200)throw Error('projection count limit');
const bytes=await readFile('collider.glb');
const manager=new THREE.LoadingManager();manager.setURLModifier(()=>{throw Error('External geometry resources forbidden');});
const parsed=await new GLTFLoader(manager).parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
parsed.scene.traverse(o=>{if(o.isMesh)o.material=new THREE.MeshBasicMaterial({side:THREE.DoubleSide});});
const group=new THREE.Group();group.scale.setScalar(input.scale);group.quaternion.set(1,0,0,0);group.position.y=input.ground;group.add(parsed.scene);group.updateMatrixWorld(true);
const radians=THREE.MathUtils.degToRad,q=new THREE.Quaternion().setFromEuler(new THREE.Euler(radians(input.pitch),radians(input.yaw),radians(input.roll),'YXZ'));
const origin=new THREE.Vector3(input.origin.x,input.origin.y,input.origin.z),ray=new THREE.Raycaster();
const positions=input.nodes.map(n=>{if(n.preserve)return {object_id:n.object_id,point:n.point};const yaw=radians(n.yaw),pitch=radians(n.pitch);ray.set(origin,new THREE.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch)).applyQuaternion(q));const hit=ray.intersectObject(parsed.scene,true)[0];return {object_id:n.object_id,point:hit?{x:hit.point.x,y:hit.point.y,z:hit.point.z}:null};});
process.stdout.write(JSON.stringify({positions}));
