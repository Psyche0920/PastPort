/* A one-way, unbounded vertical plane through an arrow; no altitude/radius test. */
export class NavigationBoundary {
 constructor(){this.signature=null;this.armed=false;}
 crossed(camera,origin,point,fallback,enabled=true){
  const signature=[origin.x,origin.z,point.x,point.z,fallback.x,fallback.z].join(':');
  if(signature!==this.signature){this.signature=signature;this.armed=false;}
  if(!enabled){this.armed=false;return false;}
  let nx=point.x-origin.x,nz=point.z-origin.z,length=Math.hypot(nx,nz);
  if(length<.05){nx=fallback.x;nz=fallback.z;length=Math.hypot(nx,nz);}
  if(!Number.isFinite(length)||length<1e-8)return false;
  const side=((camera.x-point.x)*nx+(camera.z-point.z)*nz)/length;
  if(side<=-.05)this.armed=true;
  if(this.armed&&side>=.05){this.armed=false;return true;}
  return false;
 }
}
