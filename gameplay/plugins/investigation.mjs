/** Bounded investigation activities. The host owns source receipts and Story rewards. */
export const investigationKinds=Object.freeze(['spot-difference','timeline','image-puzzle','scene-search']);
export const isInvestigation=kind=>investigationKinds.includes(kind);
const check=(test,message)=>{if(!test)throw new TypeError('Investigation: '+message);};
const ids=items=>Array.isArray(items)&&items.length>0&&items.length<=12&&new Set(items.map(i=>i.id)).size===items.length&&items.every(i=>typeof i.id==='string'&&/^[a-z0-9-]{1,64}$/.test(i.id));
const text=v=>v&&['en',v.tr?'tr':'zh'].every(l=>typeof v[l]==='string'&&v[l].trim());
const asset=v=>typeof v==='string'&&/^[a-zA-Z0-9_./-]+\.(svg|png|jpg|jpeg|webp)$/.test(v)&&!v.startsWith('/')&&!v.split('/').includes('..');
const region=r=>Array.isArray(r)&&r.length===4&&r.every(Number.isInteger)&&r[0]>=0&&r[1]>=0&&r[2]>0&&r[3]>0&&r[0]+r[2]<=10000&&r[1]+r[3]<=10000;
export function validateInvestigationConfig(c){
 check(isInvestigation(c.kind)&&text(c.prompt)&&text(c.success),'kind or bilingual copy missing');
 check(c.content_kind==='original_fiction'||c.content_kind==='source_attributed','content provenance missing');
 if(c.kind==='spot-difference')check(asset(c.left_image)&&asset(c.right_image)&&ids(c.differences)&&c.differences.length<=6&&c.differences.every(d=>region(d.left)&&region(d.right)&&text(d.label)),'invalid image pair/regions');
 if(c.kind==='timeline'){check(ids(c.cards)&&ids(c.slots)&&c.cards.length===c.slots.length&&c.cards.every(i=>text(i.text)&&c.slots.some(s=>s.id===i.target_slot))&&c.slots.every(s=>text(s.label))&&new Set(c.cards.map(i=>i.target_slot)).size===c.cards.length,'invalid timeline mapping');}
 if(c.kind==='image-puzzle')check(Number.isInteger(c.columns)&&c.columns>=2&&c.columns<=4&&Number.isInteger(c.rows)&&c.rows>=2&&c.rows<=3&&ids(c.pieces)&&c.pieces.length===c.columns*c.rows&&c.pieces.every(i=>Number.isInteger(i.target_slot)&&i.target_slot>=0&&i.target_slot<c.pieces.length)&&new Set(c.pieces.map(i=>i.target_slot)).size===c.pieces.length&&['en',c.image?.tr?'tr':'zh'].every(l=>asset(c.image?.[l])),'invalid image tile mapping');
 if(c.kind==='scene-search')check(Array.isArray(c.targets)&&c.targets.length>=2&&c.targets.length<=8&&new Set(c.targets.map(t=>t.number)).size===c.targets.length&&c.targets.every(t=>Number.isSafeInteger(t.number)&&t.number>0&&text(t.clue)),'invalid search targets');
}
function arranged(c,s){const items=c.kind==='timeline'?c.cards:c.pieces;return items.every(i=>s.placements.some(p=>p.id===i.id&&p.slot===i.target_slot));}
export function validateInvestigationState(c,s){
 check(s.cursor===0&&s.seen.length<=12,'unexpected cursor/seen state');
 if(['timeline','image-puzzle'].includes(c.kind)){
  const items=c.kind==='timeline'?c.cards:c.pieces;
  check(s.placements.length<=items.length&&new Set(s.placements.map(p=>p.id)).size===s.placements.length&&new Set(s.placements.map(p=>p.slot)).size===s.placements.length,'duplicate placement');
  check(s.placements.every(p=>p&&Object.keys(p).sort().join(',')==='id,slot'&&items.some(i=>i.id===p.id)&&(c.kind==='timeline'?c.slots.some(x=>x.id===p.slot):Number.isInteger(p.slot)&&p.slot>=0&&p.slot<items.length)),'unknown piece or slot');
  check(s.selected===null||items.some(i=>i.id===s.selected),'unknown selected piece');check(s.seen.length===0&&(!s.done||arranged(c,s)),'invalid arrangement completion');
 }else{
  const expected=c.kind==='spot-difference'?c.differences.map(d=>d.id):c.targets.map(t=>String(t.number));
  check(s.placements.length===0&&s.selected===null&&s.seen.every(id=>expected.includes(id))&&s.done===(s.seen.length===expected.length),'invalid found state');
 }
}
export function reduceInvestigation(c,s,cmd){
 let message='';
 if(c.kind==='spot-difference'){
  check(cmd.kind==='find-difference'&&['left','right'].includes(cmd.panel)&&Number.isInteger(cmd.x)&&Number.isInteger(cmd.y)&&cmd.x>=0&&cmd.x<=10000&&cmd.y>=0&&cmd.y<=10000,'invalid image coordinates');
  const hit=c.differences.find(d=>{const[x,y,w,h]=d[cmd.panel];return cmd.x>=x&&cmd.x<=x+w&&cmd.y>=y&&cmd.y<=y+h;});
  if(hit){if(!s.seen.includes(hit.id))s.seen.push(hit.id);message='found';}else{s.attempts++;message='not-a-difference';}s.done=s.seen.length===c.differences.length;
 }else if(['timeline','image-puzzle'].includes(c.kind)){
  const items=c.kind==='timeline'?c.cards:c.pieces;
  if(cmd.kind==='select-piece'){check(items.some(i=>i.id===cmd.id),'unknown piece');s.selected=cmd.id;}
  else if(cmd.kind==='place-piece'){
   check(items.some(i=>i.id===cmd.id)&&(c.kind==='timeline'?c.slots.some(x=>x.id===cmd.slot):Number.isInteger(cmd.slot)&&cmd.slot>=0&&cmd.slot<items.length),'invalid placement');
   s.placements=s.placements.filter(p=>p.id!==cmd.id&&p.slot!==cmd.slot);s.placements.push({id:cmd.id,slot:cmd.slot});s.selected=null;
  }else if(cmd.kind==='remove-piece'){check(items.some(i=>i.id===cmd.id),'unknown piece');s.placements=s.placements.filter(p=>p.id!==cmd.id);}
  else if(cmd.kind==='check-arrangement'){if(arranged(c,s)){s.done=true;message='correct';}else{s.attempts++;message=s.placements.length<items.length?'incomplete-arrangement':'wrong-arrangement';}}
  else if(cmd.kind==='clear-arrangement'){s.placements=[];s.selected=null;}
  else check(false,'unknown arrangement command');
 }else{
  check(cmd.kind==='complete-search'&&Array.isArray(cmd.verified_numbers),'search requires host source receipts');
  check(c.targets.every(t=>cmd.verified_numbers.includes(t.number)),'missing search receipt');s.seen=c.targets.map(t=>String(t.number));s.done=true;message='correct';
 }
 return message;
}
