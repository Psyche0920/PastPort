/** Preserve source navigation poses; screen bearings are camera-relative UI only. */
export function sourceArrival(value){
  const url=new URL(value);
  if(!url.searchParams.has('arrival_yaw')||!url.searchParams.has('arrival_pitch'))return null;
  const yaw=Number(url.searchParams.get('arrival_yaw')),pitch=Number(url.searchParams.get('arrival_pitch'));
  if(!Number.isFinite(yaw)||!Number.isFinite(pitch)||Math.abs(yaw)>180||Math.abs(pitch)>90)throw new RangeError('Invalid source arrival pose');
  return Object.freeze({yaw,pitch});
}
export function screenBearing(local,projected){
  if(local.z>=0)return local.x<=0?'↶':'↷';
  if(projected.x<-.8)return '←';
  if(projected.x>.8)return '→';
  if(projected.y>.8)return '↑';
  if(projected.y<-.8)return '↓';
  return '◆';
}
