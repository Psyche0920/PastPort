/** DOM-only activities: no additional 3D assets, render loops or Story mutation. */
export function renderInvestigation(root,c,state,{locale='zh',send,verifiedSources=[],feedback='',review=()=>{},explore=()=>{}}){
 const t=(zh,en)=>locale==='en'?en:zh,copy=v=>v?.[locale]??v??'';
 const el=(tag,attrs={},children=[])=>{const n=document.createElement(tag);for(const[k,v]of Object.entries(attrs)){if(k.startsWith('on'))n[k]=v;else if(k==='text')n.textContent=v;else if(k==='class')n.className=v;else if(k==='disabled')n.disabled=v;else n.setAttribute(k,v);}for(const child of children)n.append(child);return n;};
 root.classList.add('investigation-activity');
 root.append(el('h3',{text:copy(c.prompt)}));
 if(state.done){root.append(el('p',{class:'activity-success',text:copy(c.success)}));if(c.kind==='image-puzzle')root.append(el('img',{class:'restored-chat',src:copy(c.image),alt:t('重組後嘅完整圖像','The reconstructed image')}));return;}
 const feedbacks={
  'not-a-difference':t('呢個位置兩幅圖冇指定差異。再仔細比較，冇倒數。','No marked difference here. Compare the two images closely. There is no timer.'),
  'wrong-arrangement':t('仲未吻合。對照圖像接縫，或者時間卡上嘅已知時間；唔知道嘅唔好估。','Not yet. Compare image edges or the times on the cards. Keep unknown times unknown.'),
  'incomplete-arrangement':t('仲有卡片未放好。每個位置放一張，再核對。','Some cards are still unplaced. Fill each position, then check.')};
 if(feedbacks[feedback])root.append(el('p',{class:'activity-feedback',role:'status',text:feedbacks[feedback]}));
 if(c.kind==='spot-difference'){
  root.append(el('p',{text:t(`已找到 ${state.seen.length} / ${c.differences.length}。點左右圖都可以。同一處只計一次。`,`Found ${state.seen.length} / ${c.differences.length}. Select either image. Each difference counts once.`)}),el('p',{class:'muted',text:t('鍵盤：Tab 選圖，方向鍵移動圈圈，Enter 標記。','Keyboard: Tab to an image, arrow keys move the cursor, Enter marks a point.')}));
  const pair=el('div',{class:'difference-pair'});
  for(const panel of ['left','right']){
   let cursor={x:5000,y:5000};
   const image=el('img',{src:panel==='left'?c.left_image:c.right_image,alt:t(panel==='left'?'左圖：版本 A':'右圖：版本 B',panel==='left'?'Left image: version A':'Right image: version B'),draggable:'false'});
   const cursorNode=el('span',{class:'difference-cursor','aria-hidden':'true',style:'left:50%;top:50%'});
   const button=el('button',{class:'difference-image','aria-label':t(panel==='left'?'標記左圖差異':'標記右圖差異',panel==='left'?'Mark a difference on the left':'Mark a difference on the right'),onclick:event=>{const r=image.getBoundingClientRect();const x=event.detail===0?cursor.x:Math.round((event.clientX-r.left)/r.width*10000),y=event.detail===0?cursor.y:Math.round((event.clientY-r.top)/r.height*10000);if(x>=0&&x<=10000&&y>=0&&y<=10000)send({kind:'find-difference',panel,x,y});},onkeydown:event=>{const deltas={ArrowLeft:[-300,0],ArrowRight:[300,0],ArrowUp:[0,-300],ArrowDown:[0,300]};if(deltas[event.key]){event.preventDefault();cursor.x=Math.max(0,Math.min(10000,cursor.x+deltas[event.key][0]));cursor.y=Math.max(0,Math.min(10000,cursor.y+deltas[event.key][1]));cursorNode.style.left=cursor.x/100+'%';cursorNode.style.top=cursor.y/100+'%';}}},[image,cursorNode]);
   for(const d of c.differences.filter(d=>state.seen.includes(d.id))){const[x,y,w,h]=d[panel];button.append(el('span',{class:'found-difference','aria-hidden':'true',style:`left:${x/100}%;top:${y/100}%;width:${w/100}%;height:${h/100}%`}));}
   pair.append(el('figure',{},[el('figcaption',{text:panel==='left'?t('版本 A','Version A'):t('版本 B','Version B')}),button]));
  }
  root.append(pair);for(const d of c.differences.filter(d=>state.seen.includes(d.id)))root.append(el('p',{class:'found-note',text:'✓ '+copy(d.label)}));
 }else if(c.kind==='timeline'||c.kind==='image-puzzle'){
  const puzzle=c.kind==='image-puzzle',items=puzzle?c.pieces:c.cards;
  root.append(el('p',{text:puzzle?t('拖圖片碎片到格仔；亦可先點碎片，再點位置。全部放好後按核對。','Drag image fragments into the grid, or select a fragment and then a position. Check when every tile is placed.'):(c.slots.some(slot=>slot.id==='unknown')?t('拖卡片到時間位置，或者先點卡片再點位置。未知道時間嘅放「時間未明」。','Drag cards into time positions, or select a card then a position. Put uncertain events in “Time unknown”.'):t('拖卡片到時間位置，或者先點卡片再點位置。','Drag cards into time positions, or select a card then a position.'))}));
  const tile=(item,placed=false)=>{
   const attrs={class:'activity-piece'+(state.selected===item.id?' selected':''),draggable:'true','aria-pressed':String(state.selected===item.id),'aria-label':puzzle?t('圖片碎片 '+(items.indexOf(item)+1),'Image fragment '+(items.indexOf(item)+1)):copy(item.text),ondragstart:e=>{e.dataTransfer.setData('text/plain',item.id);e.dataTransfer.effectAllowed='move';},onclick:()=>send({kind:'select-piece',id:item.id})};
   if(puzzle){const col=item.target_slot%c.columns,row=Math.floor(item.target_slot/c.columns);attrs.style=`background-image:url("${copy(c.image)}");background-size:${c.columns*100}% ${c.rows*100}%;background-position:${col/(c.columns-1)*100}% ${row/(c.rows-1)*100}%`;}
   const button=el('button',attrs);if(!puzzle)button.textContent=copy(item.text);else button.append(el('span',{class:'sr-only',text:attrs['aria-label']}));
   if(placed)button.title=t('可拖走或重新選取','Drag or select to move');return button;
  };
  const bank=el('div',{class:puzzle?'image-piece-bank':'timeline-bank','aria-label':t('未放置卡片','Unplaced pieces')});
  for(const item of items.filter(item=>!state.placements.some(p=>p.id===item.id)))bank.append(tile(item));
  const board=el('div',{class:puzzle?'image-puzzle-board':'timeline-board',role:'group','aria-label':t('重建區域','Reconstruction area'),...(puzzle?{style:`grid-template-columns:repeat(${c.columns},1fr)`}:{})});
  const slots=puzzle?Array.from({length:items.length},(_,id)=>({id,label:null})):c.slots;
  slots.forEach((slot,index)=>{
   const place=id=>{if(id)send({kind:'place-piece',id,slot:slot.id});};
   const cell=el('div',{class:'activity-slot',ondragover:e=>{e.preventDefault();e.dataTransfer.dropEffect='move';},ondrop:e=>{e.preventDefault();place(e.dataTransfer.getData('text/plain'));}});
   if(!puzzle)cell.append(el('strong',{text:copy(slot.label)}));
   const placed=state.placements.find(p=>p.slot===slot.id);
   if(placed){cell.append(tile(items.find(i=>i.id===placed.id),true),el('button',{class:'remove-piece',text:t('取回','Remove'),onclick:()=>send({kind:'remove-piece',id:placed.id})}));}
   else cell.append(el('button',{class:'empty-slot',text:puzzle?String(index+1):t('放喺呢度','Place here'),'aria-label':puzzle?t('放到位置 '+(index+1),'Place in position '+(index+1)):copy(slot.label),onclick:()=>place(state.selected)}));
   board.append(cell);
  });
  root.append(el('div',{class:'arrangement-layout'+(puzzle?' is-image-layout':'')},[bank,board]),el('div',{class:'activity-controls'},[el('button',{text:t('清空重排','Clear arrangement'),onclick:()=>send({kind:'clear-arrangement'})}),el('button',{class:'primary',text:t('核對重建結果 →','Check reconstruction →'),onclick:()=>send({kind:'check-arrangement'})})]));
 }else{
  root.append(el('p',{text:t('收起此窗，轉動視角，點場景中物件嘅編號，再確認記錄。清單本身唔會代你收集。','Close this panel, look around and select object numbers in the scene, then record the find. The checklist cannot collect items for you.')}));
  for(const target of c.targets)root.append(el('p',{class:verifiedSources.includes(target.number)?'found-note':'search-clue',text:(verifiedSources.includes(target.number)?'✓ ':'○ ')+copy(target.clue)}));
  root.append(el('button',{text:t('返回場景搜尋','Search the scene'),onclick:explore}));
  if(c.targets.every(t=>verifiedSources.includes(t.number)))root.append(el('button',{class:'primary',text:t('整理已找到嘅物件 →','Complete the search →'),onclick:()=>send({kind:'complete-search'})}));
 }
 root.append(el('div',{class:'activity-controls'},[el('button',{text:t('重看案件背景','Review case context'),onclick:review}),el('button',{text:t('暫停小遊戲，保留進度','Close activity and keep progress'),onclick:explore})]));
}
