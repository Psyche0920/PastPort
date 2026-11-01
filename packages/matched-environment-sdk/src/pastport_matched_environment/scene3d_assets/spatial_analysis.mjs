/** Offline advisory geometry analysis; never changes player state or collision rules. */
import * as THREE from './three.module.js';
import {GLTFLoader} from './GLTFLoader.js';
import {readFile} from 'node:fs/promises';

export const POLICY = Object.freeze({version:'pastport.geometry-direct/1', spacing:.2,
  maximumStep:.35, maximumDistance:20, standoff:1.4, minimumEye:.35, maximumEye:1.6});

/** Static world-space triangle tree; accelerates repeated rays without changing geometry. */
export class TriangleIndex {
  constructor(root) {
    const triangles=[];
    root.updateMatrixWorld(true);
    root.traverse(mesh=>{
      if(!mesh.isMesh)return;
      const position=mesh.geometry.attributes.position,index=mesh.geometry.index;
      const count=index?index.count:position.count;
      for(let i=0;i<count;i+=3){
        const vertices=[0,1,2].map(j=>new THREE.Vector3().fromBufferAttribute(
          position,index?index.getX(i+j):i+j).applyMatrix4(mesh.matrixWorld));
        const box=new THREE.Box3().setFromPoints(vertices);
        triangles.push({vertices,box,center:box.getCenter(new THREE.Vector3()),
          normal:new THREE.Triangle(...vertices).getNormal(new THREE.Vector3())});
      }
    });
    if(triangles.length>300000)throw Error('triangle limit');
    this.root=this.build(triangles);
  }
  build(items) {
    const box=new THREE.Box3();for(const item of items)box.union(item.box);
    if(items.length<=16)return {box,items};
    const size=box.getSize(new THREE.Vector3());
    const axis=size.x>=size.y&&size.x>=size.z?'x':size.y>=size.z?'y':'z';
    items.sort((a,b)=>a.center[axis]-b.center[axis]);const middle=Math.floor(items.length/2);
    return {box,left:this.build(items.slice(0,middle)),right:this.build(items.slice(middle))};
  }
  hits(caster) {
    const hits=[],scratch=new THREE.Vector3();
    const visit=node=>{
      if(!caster.ray.intersectsBox(node.box))return;
      if(node.items){for(const triangle of node.items){
        const point=caster.ray.intersectTriangle(...triangle.vertices,false,scratch);
        if(!point)continue;
        const distance=point.distanceTo(caster.ray.origin);
        if(distance>=caster.near&&distance<=caster.far)
          hits.push({point:point.clone(),normal:triangle.normal,distance});
      }}else{visit(node.left);visit(node.right);}
    };
    visit(this.root);return hits.sort((a,b)=>a.distance-b.distance);
  }
}

export class SpatialAnalyzer {
  constructor(collider, policy=POLICY) { this.collider=collider; this.policy=policy; this.index=new TriangleIndex(collider); }
  floor(point) {
    const ray=new THREE.Raycaster(new THREE.Vector3(point.x,point.y+1,point.z),
      new THREE.Vector3(0,-1,0),0,4);
    return this.index.hits(ray).find(hit=>Math.abs(hit.normal.y)>.7)?.point;
  }
  segment(from,to,eye) {
    const delta=to.clone().sub(from),distance=delta.length();
    if(distance<.001)return true;
    for(const offset of [-Math.max(.1,eye-.12),-eye*.5,0]) {
      const start=from.clone();start.y+=offset;
      if(this.index.hits(new THREE.Raycaster(start,delta.clone().normalize(),0,distance+.2))
        .length)return false;
    }
    return true;
  }
  direct(from,target,eye,standoff=0) {
    const end=target.clone();end.y=from.y;
    const delta=end.clone().sub(from),length=delta.length();
    if(length>this.policy.maximumDistance)return {status:'distance_limit',points:[]};
    end.copy(from).addScaledVector(delta,Math.max(0,(length-standoff)/Math.max(length,.001)));
    const steps=Math.max(1,Math.ceil(from.distanceTo(end)/this.policy.spacing)),points=[];
    let previous=from;
    for(let i=1;i<=steps;i++) {
      const point=from.clone().lerp(end,i/steps),floor=this.floor(point);
      if(!floor)return {status:'ground_unknown',points:[]};
      point.y=floor.y+eye;
      if(Math.abs(point.y-previous.y)>this.policy.maximumStep||!this.segment(previous,point,eye))
        return {status:'direct_obstructed',points:[]};
      points.push(point);previous=point;
    }
    return {status:'clear',points};
  }
  sight(from,target) {
    const delta=target.clone().sub(from),distance=delta.length();
    if(distance<.05)return 'target_too_close';
    // A ray to an anchor is geometry evidence, not proof of object identity, glass
    // transparency, object silhouette or readability of an inscription.
    const hit=this.index.hits(new THREE.Raycaster(
      from,delta.normalize(),0,Math.max(0,distance-.15)))[0];
    return hit?'collider_occluded':'clear_to_anchor';
  }
  run(input) {
    const origin=new THREE.Vector3(input.origin.x,input.origin.y,input.origin.z);
    const floor=this.floor(origin),eye=floor?
      Math.max(this.policy.minimumEye,Math.min(this.policy.maximumEye,origin.y-floor.y)):1.6;
    const spawn=origin.clone();if(floor)spawn.y=floor.y+eye;
    const sources=new Map([['spawn',spawn]]),objects=[];
    for(const node of input.nodes) {
      const target=node.point?new THREE.Vector3(node.point.x,node.point.y,node.point.z):null;
      const route=target&&floor?this.direct(spawn,target,eye,this.policy.standoff):
        {status:target?'ground_unknown':'missing_position',points:[]};
      const approach=route.status==='clear'?route.points.at(-1):null;
      if(approach)sources.set(node.key,approach);
      objects.push({key:node.key,route_status:route.status,
        route:route.points.map(p=>({x:p.x,y:p.y,z:p.z})),
        sight:target?this.sight(spawn,target):'missing_position',
        distance:target?spawn.distanceTo(target):null,
        legibility:'unknown',touch:'unknown'});
    }
    for(let i=0;i<objects.length;i++) {
      const node=input.nodes[i],target=node.point?
        new THREE.Vector3(node.point.x,node.point.y,node.point.z):null;
      const observation_positions=[];
      if(target&&floor)for(const [station,point] of sources){
        observation_positions.push({station,point:{x:point.x,y:point.y,z:point.z},
          distance:point.distanceTo(target),sight:this.sight(point,target)});
      }
      objects[i].planning={basis:'registered_geometry_not_identity_approval',
        observation_positions,approach_station:sources.has(node.key)?node.key:null,
        enabled_interactions:node.interactions??[],
        detail_reading:'task_specific_requirement_missing',
        physical_touch:'host_touch_rule_not_registered'};
    }
    const routes=[];
    // Every ordered transition between geometrically reachable approach locations
    // is checked independently. No transitivity assumption across obstacles.
    for(const [source,from] of sources)for(const [target,to] of sources) {
      if(source===target)continue;
      const route=this.direct(from,to,eye);
      routes.push({source,target,status:route.status,
        points:route.points.map(p=>({x:p.x,y:p.y,z:p.z}))});
    }
    return {policy_version:this.policy.version,spawn_ground:!!floor,
      spawn:{x:spawn.x,y:spawn.y,z:spawn.z},eye_height:eye,objects,routes};
  }
}

async function main() {
  let text='';
  for await(const chunk of process.stdin){text+=chunk;if(text.length>1024*1024)throw Error('input limit');}
  const input=JSON.parse(text);
  if(input.nodes.length>100)throw Error('node limit');
  const bytes=await readFile('collider.glb');
  const manager=new THREE.LoadingManager();
  manager.setURLModifier(()=>{throw Error('External geometry resources forbidden');});
  const parsed=await new GLTFLoader(manager).parseAsync(
    bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
  parsed.scene.traverse(o=>{if(o.isMesh)o.material=new THREE.MeshBasicMaterial({side:THREE.DoubleSide});});
  const group=new THREE.Group();group.scale.setScalar(input.metric_scale_factor);
  group.quaternion.set(1,0,0,0);group.position.y=input.ground_plane_offset;
  group.add(parsed.scene);group.updateMatrixWorld(true);
  const result=new SpatialAnalyzer(group).run(input);
  process.stdout.write(JSON.stringify(result));
}
if(process.argv.includes('--run'))await main();
