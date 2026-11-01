/** Story-side interaction contract; the scene host alone owns navigation. */
export class SceneStoryBridge {
  constructor({sceneIds,objectIds,send,inspect,arrive,radius=1.8}) {
    if(!Number.isFinite(radius)||radius<=0)throw new RangeError('Invalid arrival radius');
    this.sceneIds=new Set(sceneIds);this.objectIds=new Set(objectIds);
    this.send=send;this.inspect=inspect;this.arrive=arrive;this.radius=radius;
    this.scene=null;this.markers=new Map();this.pending=null;this.sequence=0;
  }
  attach({sceneId,binding,markers}) {
    if(!this.sceneIds.has(sceneId)||typeof binding!=='string'||!binding)throw new Error('Unknown scene identity');
    const next=new Map();
    for(const marker of markers) {
      if(!this.objectIds.has(marker.number)||next.has(marker.number)||!validPoint(marker.position))throw new Error('Invalid scene marker');
      next.set(marker.number,Object.freeze({...marker,position:Object.freeze([...marker.position])}));
    }
    this.scene=Object.freeze({sceneId,binding});this.markers=next;this.pending=null;this.sequence++;
  }
  click(number) {
    if(!this.markers.has(number))return false;
    this.cancel();this.inspect(number);return true;
  }
  approach(number) {
    const marker=this.markers.get(number);
    if(!marker||marker.navigationReviewed!==true)return false;
    this.pending=Object.freeze({number,token:++this.sequence,...this.scene});
    this.send({...this.pending,type:'story:approach',position:[...marker.position]});
    return true;
  }
  update({sceneId,binding,token,position,routeComplete}) {
    const pending=this.pending;
    if(!pending||pending.sceneId!==sceneId||pending.binding!==binding||pending.token!==token||routeComplete!==true||!validPoint(position))return false;
    const target=this.markers.get(pending.number).position;
    if(Math.hypot(position[0]-target[0],position[2]-target[2])>this.radius)return false;
    this.pending=null;this.arrive(pending.number);return true;
  }
  cancel() {if(this.pending){this.send({...this.pending,type:'story:cancel'});this.pending=null;}}
}
function validPoint(value){return Array.isArray(value)&&value.length===3&&value.every(Number.isFinite);}
