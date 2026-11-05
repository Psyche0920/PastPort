/** A bounded 2D guide in the renderer's frame; it grants no source observations. */
const NS = 'http://www.w3.org/2000/svg';
const finite = value => typeof value === 'number' && Number.isFinite(value);
export function mapLayout(message, allowedNumbers) {
  const b = message?.bounds;
  if (!b || !['minX','maxX','minZ','maxZ'].every(k => finite(b[k])) ||
      b.maxX <= b.minX || b.maxZ <= b.minZ || b.maxX-b.minX > 10000 || b.maxZ-b.minZ > 10000 ||
      !Array.isArray(message.objects) || message.objects.length > 256) return null;
  const allowed = new Set(allowedNumbers), seen = new Set(), objects = [];
  for (const item of message.objects) {
    if (!item || !Number.isSafeInteger(item.number) || !allowed.has(item.number) || seen.has(item.number) ||
        !finite(item.x) || !finite(item.z)) return null;
    seen.add(item.number); objects.push({number:item.number,x:item.x,z:item.z});
  }
  return {bounds:{minX:b.minX,maxX:b.maxX,minZ:b.minZ,maxZ:b.maxZ},objects};
}
export function projectMapPoint(bounds, point, clamp=true) {
  if (!point || !finite(point.x) || !finite(point.z)) return null;
  const width=bounds.maxX-bounds.minX,height=bounds.maxZ-bounds.minZ;
  const scale=156/Math.max(width,height), left=(180-width*scale)/2, top=(180-height*scale)/2;
  const x=left+(point.x-bounds.minX)*scale,y=top+(point.z-bounds.minZ)*scale;
  return {x:clamp?Math.max(8,Math.min(172,x)):x,y:clamp?Math.max(8,Math.min(172,y)):y};
}
export class RoomMinimap {
  constructor({parent,allowedNumbers,mapSymbols=[],getLocale=()=> 'zh'}) {
    Object.assign(this,{allowedNumbers,getLocale}); this.layout=null; this.nodes=new Map();this.symbols=new Map(mapSymbols.map(item=>[item.number,item]));
    this.root=document.createElement('aside');this.root.className='room-minimap';this.root.hidden=true;
    this.toggle=document.createElement('button');this.toggle.type='button';this.toggle.setAttribute('aria-expanded','true');
    this.body=document.createElement('div');this.body.id='room-minimap-body';this.toggle.setAttribute('aria-controls',this.body.id);
    this.svg=document.createElementNS(NS,'svg');this.svg.setAttribute('viewBox','0 0 180 180');this.svg.setAttribute('role','img');
    const grid=document.createElementNS(NS,'path');grid.setAttribute('d','M12 12H168V168H12ZM51 12V168M90 12V168M129 12V168M12 51H168M12 90H168M12 129H168');grid.setAttribute('class','minimap-grid');
    this.points=document.createElementNS(NS,'g');this.player=document.createElementNS(NS,'path');this.player.setAttribute('d','M0 -8L6 6L0 3L-6 6Z');this.player.setAttribute('class','minimap-player');this.player.style.display='none';
    this.floor=document.createElementNS(NS,'path');this.floor.setAttribute('class','minimap-floor');this.floor.setAttribute('d','M10 10H170V170H10Z');
    this.svg.append(this.floor,this.points,this.player);this.note=document.createElement('p');this.legend=document.createElement('p');this.legend.className='minimap-legend';this.expand=document.createElement('button');this.expand.type='button';this.expand.className='minimap-expand';this.expand.onclick=()=>{this.large=!this.large;this.root.className='room-minimap'+(this.large?' is-expanded':'');this.expand.setAttribute('aria-pressed',String(Boolean(this.large)));this.setLocale();};this.key=document.createElement('p');this.key.className='minimap-key';this.body.append(this.svg,this.legend,this.key,this.note,this.expand);this.root.append(this.toggle,this.body);parent.append(this.root);
    this.toggle.onclick=()=>{this.body.hidden=!this.body.hidden;this.toggle.setAttribute('aria-expanded',String(!this.body.hidden));this.setLocale();};this.setLocale();
  }
  t(zh,en){return this.getLocale()==='en'?en:zh;}
  setLocale(){this.root.setAttribute('aria-label',this.t('房間小地圖','Room minimap'));this.toggle.textContent=this.t('房間導覽','Room guide')+(this.body.hidden?' ＋':' −');this.svg.setAttribute('aria-label',this.t('你的方向及物件編號位置示意','Your direction and approximate object positions'));this.legend.textContent=this.t('▲ 你　金色：目前目標','▲ You · Gold: current target');this.note.textContent=this.t('房間平面示意 · 非量度圖','Room plan · schematic, not to scale');this.key.textContent=[...this.symbols].map(([n,item])=>`${String(n).padStart(2,'0')} ${item.label?.[this.getLocale()]??''}`).join(' · ');this.expand.textContent=this.large?this.t('縮小地圖 ↙','Smaller map ↙'):this.t('放大地圖 ↗','Larger map ↗');}
  setLayout(message){const layout=mapLayout(message,this.allowedNumbers);if(!layout)return;this.layout=layout;this.viewBounds=null;this.points.replaceChildren();this.nodes.clear();for(const object of layout.objects){const p=projectMapPoint(layout.bounds,object),group=document.createElementNS(NS,'g');group.setAttribute('transform',`translate(${p.x} ${p.y})`);const circle=document.createElementNS(NS,'circle');circle.setAttribute('r','4');const label=document.createElementNS(NS,'text');label.setAttribute('dy','.35em');label.textContent=String(object.number).padStart(2,'0');const symbol=this.symbols.get(object.number);const icon=document.createElementNS(NS,'path');icon.setAttribute('class','minimap-fixture');const shapes={table:'M-11 0a11 8 0 1 0 22 0a11 8 0 1 0 -22 0',chair:'M-6 -5H6V5H-6ZM-7 -8H7M-7 -8V-3M7 -8V-3',board:'M-11 -2H11V2H-11ZM-7 2V6M7 2V6',shelf:'M-10 -5H10V5H-10ZM-3 -5V5M3 -5V5',laptop:'M-5 -4H5V3H-5ZM-7 5H7'};icon.setAttribute('d',shapes[symbol?.symbol]??'M-4 -4H4V4H-4Z');const title=document.createElementNS(NS,'title');title.textContent=symbol?.label?.[this.getLocale()]??String(object.number);group.append(icon,circle,label,title);this.points.append(group);this.nodes.set(object.number,group);}}
  updatePose(pose){if(!this.layout||!finite(pose?.dx)||!finite(pose?.dz)||!finite(pose.x)||!finite(pose.z))return;this.fitView(pose);const p=projectMapPoint(this.viewBounds,pose);if(!p)return;this.player.style.display='';const angle=Math.atan2(pose.dx,-pose.dz)*180/Math.PI;this.player.setAttribute('transform',`translate(${p.x} ${p.y}) rotate(${angle})`);}
  fitView(pose){
    const b=this.layout.bounds,items=[...this.layout.objects,pose];
    if(!finite(pose.x)||!finite(pose.z))return;
    if(this.viewBounds&&pose.x>=this.viewBounds.minX&&pose.x<=this.viewBounds.maxX&&pose.z>=this.viewBounds.minZ&&pose.z<=this.viewBounds.maxZ)return;
    const xs=items.map(p=>p.x),zs=items.map(p=>p.z),span=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...zs)-Math.min(...zs),(b.maxX-b.minX)*.02,(b.maxZ-b.minZ)*.02),pad=span*.2;
    this.viewBounds={minX:Math.min(...xs)-pad,maxX:Math.max(...xs)+pad,minZ:Math.min(...zs)-pad,maxZ:Math.max(...zs)+pad};
    const labels=[];
    for(const object of this.layout.objects){const point=projectMapPoint(this.viewBounds,object),node=this.nodes.get(object.number);node.setAttribute('transform',`translate(${point.x} ${point.y})`);let y=-11;while(labels.some(p=>Math.hypot(p.x-point.x,p.y-(point.y+y))<18))y+=18;labels.push({x:point.x,y:point.y+y});const text=node.querySelector('text');text.setAttribute('x','0');text.setAttribute('y',String(y));}
  }
  setTarget(number){for(const[id,node]of this.nodes)node.setAttribute('class',id===number?'minimap-target':'');}
  setVisible(visible){const hidden=!visible||!this.layout;if(this.root.hidden!==hidden)this.root.hidden=hidden;}
  destroy(){this.root.remove();}
}
