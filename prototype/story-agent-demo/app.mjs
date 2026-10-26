import {DialoguePlayer,openingLines,spokenCopy} from './dialogue.mjs';
import {validateNavigation} from './navigation.mjs';
import {GameSession} from './session.mjs';
import {CinematicView} from './cinematic-view.mjs?rev=ui3-navigation-dialogue';
import {Scene3DView} from './scene3d-view.mjs';
const use3D=new URLSearchParams(location.search).get('scene')==='3d';
const $=selector=>document.querySelector(selector);
const element=(tag,attributes={},children=[])=>{const node=document.createElement(tag);for(const[key,value]of Object.entries(attributes)){if(key==='text')node.textContent=value;else if(key==='class')node.className=value;else if(key.startsWith('on'))node.addEventListener(key.slice(2),value);else if(typeof value==='boolean'){if(value)node.setAttribute(key,'');}else node.setAttribute(key,String(value));}for(const child of children)node.append(typeof child==='string'?document.createTextNode(child):child);return node;};
let locale='zh',session,busy=false,walking=false,frameReady=false,walker=null,pendingTalk=false,encounterOpen=true,selectedPiece=0,rotated=false,lastFeedback='',hintOpen=false;
let toastTimer,restoring=false,cinematic=null,dialogue=null;
const keys=new Set();const directions={up:[0,-1],down:[0,1],left:[-1,0],right:[1,0]};
const t=(zh,en)=>locale==='zh'?zh:en;
const text=value=>typeof value==='string'?value:value?.[locale]??'';
function notify(message){const box=$('#toast');box.textContent=message;box.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.hidden=true,6000);}
function controlText(){document.documentElement.lang=locale==='zh'?'zh-CN':'en';for(const n of document.querySelectorAll('[data-zh]'))n.textContent=n.dataset[locale];$('#language').textContent=locale==='zh'?'EN':'中文';$('#pause').textContent=session?.paused?t('继续','Resume'):t('暂停','Pause');$('#intro').textContent=text(session?.presentation.intro);$('#stage').dataset.pause=t('已暂停','PAUSED');}
function messageToFrame(message){$('#museum').contentWindow?.postMessage(message,location.origin);}
function stopWalker(){cinematic?.cancelMotion();}
function savePosition(){cinematic?.remember();}
function setWalk(active){if(!active)cinematic?.leave();}
function openTask(){dialogue?.suspend();render();if(!$('#story-panel').open)$('#story-panel').showModal();cinematic?.highlightSpeaker();}
function openEncounter(){
  if($('#story-panel').open)$('#story-panel').close();
  if(session.state.ending_id){openTask();return;}
  const c=session.current;let lines=[];
  if(c.plugin.kind==='dialogue'){
    for(const item of c.plugin.items){const paragraphs=text(selectedVariant(item)).split(/\n+/).filter(Boolean);paragraphs.forEach((value,index)=>lines.push({speaker:item.speaker,text:value,itemId:item.id,itemEnd:index===paragraphs.length-1,commit:c.plugin.commitments===true}));}
  }else lines=(openingLines[c.id]??[{speaker:'Yusuf',text:text(c.title)}]).map(line=>({...line}));
  lines=lines.map(line=>({...line,frame:session.presentation.castFrames[line.speaker]??1,row:session.presentation.castRows?.[line.speaker]??100}));
  dialogue.open(lines,{acknowledge:async line=>{if(line.itemEnd&&!session.entry().activity.seen.includes(line.itemId)&&!session.taskDone())await session.dispatch({kind:'read',id:line.itemId});},done:()=>openTask()});
}
function openGuide(){
  if(dialogue.active||document.querySelector('dialog[open]'))return;
  dialogue.open([
    {speaker:'İlyas',frame:0,row:100,text:t('Yusuf，你母亲Meryem在门边等你。忙完今天的差事，记得和她一起回家。','Yusuf, your mother Meryem is waiting by the entrance. Finish today’s work, then go home with her.')},
    {speaker:'İlyas',frame:0,row:100,text:t('Yusuf，你回来了。今天厨房缺柴，屋面也等着修。你先别急着答应，得问清楚人家到底要什么。','Yusuf, you are back. The kitchen needs fuel, and the roof needs repairs. Before you agree to anything, find out exactly what they need.')},
    {speaker:'İlyas',frame:0,row:100,text:t('你不是说想学认字吗？看入口上那块石头。是谁下令建的、哪一年动的工，都刻在上面。','You said you wanted to learn to read. Look at the stone above the entrance. It names the patron and records when the building work began.')},
    {speaker:'İlyas',frame:0,row:100,text:t('走，我念给你听。今天先认几个字，差事上的话，也慢慢学着听明白。','Come, I will read it to you. We can start with a few words. Learning what people mean when they give you work takes practice too.')}
  ],{done:()=>openTask()});
}
async function run(action){if(busy||restoring)return;busy=true;try{await action();}catch(error){const translations={'Piece outside board':t('板块超出边界，换个位置或转一下。','The piece is outside the board.'),'Overlapping pieces':t('这里已经有板块，换个位置。','This position overlaps another piece.'),'Piece already placed':t('这块已经放好了；可以撤回后再放。','This piece is already placed.'),'Plan unavailable':t('这项互助还没有建立，另选一种安排。','This offer is not available.')};notify(translations[error.message]??error.message);}finally{busy=false;render();}}
function sourceChip(number,required=false){const object=session.presentation.objects.find(o=>o.number===number);const seen=session.entry().sources.includes(number);return element('button',{class:`${required?'':'optional'} ${seen?'seen':''}`,text:`${seen?'✓':'ⓘ'} ${String(number).padStart(2,'0')} · ${locale==='zh'?object.historical_title:text(session.presentation.sourceNotes[number]).split(/[.;]/)[0]}`,title:object.historical_title,onclick:()=>cinematic.click(number),onkeydown:event=>{if(event.key==='Enter'){event.preventDefault();event.stopPropagation();cinematic.key(number,event.shiftKey);}}});}
function selectedVariant(item){return spokenCopy[session.current.id]?.[item.id]??item.variants?.find(v=>session.evaluate(v.guard))?.text??item.text;}
function render(){
  if(!session||restoring)return;controlText();const c=session.current,entry=session.entry(),done=session.taskDone();walking=cinematic?.active??false;encounterOpen=true;const target=session.presentation.stageTargets[c.id];$('#quest-stage').textContent=t(`第${c.chapter}章 · 本机保存`,`Chapter ${c.chapter} · saved locally`);$('#quest-title').textContent=text(c.title);$('#quest-instruction').textContent=walking?t('WASD走动 · 到达触发任务 · Esc返回环视','WASD to walk · Tasks on arrival · Esc to look around'):t(`单击看介绍，双击${String(target).padStart(2,'0')}号物件走近。`,`Click to inspect; double-click object ${target} to approach.`);cinematic?.renderActors();if(use3D)$('#locate-target').textContent=session.nextSource()===null?t('继续当前任务 →','Continue current task →'):t(`⌖ 定位${session.nextSource()}号`,`⌖ Locate ${session.nextSource()}`);
  $('#chapter-label').textContent=t(`第 ${c.chapter} / 6 章`,`CHAPTER ${c.chapter} / 6`);$('#progress-fill').style.width=`${session.state.ending_id?100:(session.presentation.chapters.findIndex(s=>s.id===c.id)/session.presentation.chapters.length)*100}%`;
  $('#save-status').textContent=session.unsaved?t('● 未保存','● Not saved'):t('✓ 本机已保存','✓ Saved locally');
  $('#mode-status').textContent=walking?t('局部固定视角 · 地面走动，走近交互','Fixed local view · walk, then interact'):t('拖动环视，点击编号看资料','Drag to look around · click numbers for sources');
  $('#stage').classList.toggle('paused',session.paused);
  const story=$('#story'),task=$('#task'),decisions=$('#decisions'),next=$('#next');story.replaceChildren();task.replaceChildren();decisions.replaceChildren();next.replaceChildren();
  const centerTask=Boolean(session.state.ending_id)||Boolean(c.decision)||['question','routing','tiling','budget'].includes(c.plugin.kind);
  $('#story-panel').classList.toggle('is-task-window',centerTask);
  $('#story-panel').classList.toggle('is-minigame',['tiling','routing'].includes(c.plugin.kind)&&!done&&session.nextSource()===null);
  if(done&&dialogue?.suspended&&$('#story-panel').open)queueMicrotask(()=>{if(session.taskDone()&&dialogue.suspended){$('#story-panel').close();dialogue.resume();}});
  if(session.state.ending_id){renderEnding(story);return;}
  story.append(element('h2',{text:text(c.title)}));
  const chips=element('div',{class:'source-chips'});for(const number of c.objects)chips.append(sourceChip(number,c.requiredSources.includes(number)));story.append(use3D?element('details',{class:'task-sources'},[element('summary',{text:t('查看相关资料','Related sources')}),chips]):chips);
  const box=element('div',{class:'task-box'});task.append(box);
  if(done){box.append(element('div',{class:'completed',text:t('本阶段已完成','Stage completed')}));}
  else {
    const missing=c.requiredSources.filter(n=>!entry.sources.includes(n));
    if(missing.length){box.append(element('h3',{text:t('先看看留下的资料','Read the surviving evidence')}),element('p',{class:'source-hint',text:t('打开下方资料，读后点击“加入本次观察”。普通浏览不会自动完成任务。','Open each source and choose “Record for this task”. Browsing alone does not complete the task.')}));for(const n of missing)box.append(sourceChip(n,true));}
    else if(session.paused)box.append(element('p',{text:t('已暂停，继续后再操作。','Paused. Resume to continue.')}));
    else renderActivity(box,c,entry.activity);
  }
  const decision=c.decision;
  if(done&&decision&&!session.decision()){
    decisions.append(element('h3',{text:t('这句话，由你来说','Choose your response')}));for(const option of c.options)decisions.append(element('button',{class:'option choice',text:text(option.text),disabled:busy||session.paused,onclick:()=>run(()=>session.choose(option.id))}));
  } else if(done&&decision){const picked=c.options.find(o=>o.id===session.decision());decisions.append(element('p',{class:'choice-note',text:t('你选择了：','You chose: ')+text(picked.text)}));}
  if(done&&(!decision||session.decision()))next.append(element('button',{class:'primary',text:t('继续 →','Continue →'),disabled:session.paused||busy,onclick:()=>run(async()=>{if(walking)setWalk(false);await session.advance();lastFeedback='';hintOpen=false;selectedPiece=0;rotated=false;$('#story-panel').scrollTop=0;})}));
}
function renderActivity(box,c,state){
  const config=c.plugin;const send=cmd=>run(async()=>{const step=await session.dispatch(cmd);lastFeedback=step.message;if(step.result.status==='completed')notify(t('已完成，结果已记下。','Completed. Your result is recorded.'));});
  if(config.kind==='question'){
    box.append(element('h3',{text:text(config.prompt)}));for(const option of config.options)box.append(element('button',{class:'option',text:text(option.text),disabled:busy,onclick:()=>send({kind:'answer',id:option.id})}));
    if(lastFeedback){const option=config.options.find(o=>o.id===lastFeedback);if(option)box.append(element('p',{class:'feedback',text:text(option.feedback)}));}
  } else if(config.kind==='routing'){
    box.append(element('h3',{text:t('工料分流','Sort the supplies')}),element('p',{text:t('看用途，把卡片送到对应队列。可拖放，也可点击或按1 / 2 / 3。','Read each purpose. Drag, click a destination, or press 1 / 2 / 3.')}));
    const card=config.cards[state.cursor],cardNode=element('div',{class:'material-card',draggable:'true',text:text(card.label),ondragstart:event=>event.dataTransfer.setData('text/plain',card.id)});box.append(element('div',{class:'card-track'},[cardNode]));
    const bins=element('div',{class:'bins'});config.bins.forEach((bin,index)=>{const node=element('button',{disabled:busy,ondragover:event=>event.preventDefault(),ondrop:event=>{event.preventDefault();if(event.dataTransfer.getData('text/plain')===card.id)send({kind:'route',bin:bin.id});},onclick:()=>send({kind:'route',bin:bin.id})},[text(bin.label),element('small',{text:String(index+1)})]);bins.append(node);});box.append(bins,element('p',{class:'muted',text:t(`第 ${state.cursor+1} / ${config.cards.length} 张 · 返工 ${state.attempts} 次`,`Card ${state.cursor+1} / ${config.cards.length} · Rework ${state.attempts}`)}));if(lastFeedback==='wrong-bin')box.append(element('p',{class:'feedback',text:t('用途对不上，卡片已退回复核。再看订单，不只看“木”字。','The use does not match. Recheck the order; “wood” alone is not enough.')}));
  } else if(config.kind==='dialogue'){box.append(element('button',{text:t('继续交谈','Continue the conversation'),onclick:()=>{$('#story-panel').close();openEncounter();}}));
  } else if(config.kind==='tiling'){
    box.append(element('h3',{text:t('临时遮护拼板','Temporary cover puzzle')}),element('p',{text:t('把六块板放进4×4区域。先选一块，再点落点；可以旋转或撤回。抽象拼板不代表实际施工。','Fit six pieces into a 4×4 area. Select a piece, then choose its top-left cell. Rotate or undo as needed. This is an abstract puzzle, not a construction plan.')}));
    const used=state.placements.map(p=>p.id);if(used.includes(selectedPiece))selectedPiece=config.pieces.findIndex((_,i)=>!used.includes(i));
    const pieces=element('div',{class:'piece-list'});config.pieces.forEach((piece,id)=>pieces.append(element('button',{class:id===selectedPiece?'selected':'',text:`${id+1} · ${piece.join('×')}${used.includes(id)?' ✓':''}`,disabled:used.includes(id)||busy,draggable:used.includes(id)?'false':'true',onclick:()=>{selectedPiece=id;render();},ondragstart:event=>{selectedPiece=id;event.dataTransfer.setData('text/plain',String(id));}})));box.append(pieces);
    const grid=element('div',{class:'board',role:'group','aria-label':t('4乘4拼板区域','4 by 4 puzzle board')});
    for(let y=0;y<4;y++)for(let x=0;x<4;x++){
      const occupant=state.placements.find(p=>{const[w,h]=p.rotated?[...config.pieces[p.id]].reverse():config.pieces[p.id];return x>=p.x&&x<p.x+w&&y>=p.y&&y<p.y+h;});
      const cell=element('button',{class:occupant?'filled':'',text:occupant?String(occupant.id+1):'·','aria-label':`${y+1}, ${x+1}${occupant?t(`：板${occupant.id+1}`,`: piece ${occupant.id+1}`):t('：空',' empty')}`,style:occupant?`--hue:${35+occupant.id*42}`:'',disabled:busy,ondragover:event=>event.preventDefault(),ondrop:event=>{event.preventDefault();const id=Number(event.dataTransfer.getData('text/plain'));if(Number.isInteger(id)&&id>=0&&id<6)send({kind:'place',id,x,y,rotated});},onclick:()=>send({kind:'place',id:selectedPiece,x,y,rotated}),onkeydown:event=>{const map={ArrowLeft:-1,ArrowRight:1,ArrowUp:-4,ArrowDown:4};if(event.key in map){event.preventDefault();grid.children[Math.max(0,Math.min(15,y*4+x+map[event.key]))].focus();}}});grid.append(cell);
    }
    box.append(grid,element('div',{class:'puzzle-controls'},[
      element('button',{text:rotated?t('方向：已旋转90°','Rotation: 90°'):t('旋转90°','Rotate 90°'),onclick:()=>{rotated=!rotated;render();}}),
      element('button',{text:t('撤回一步','Undo'),disabled:!state.placements.length||busy,onclick:()=>send({kind:'undo'})}),
      element('button',{text:t('清空','Clear'),disabled:!state.placements.length||busy,onclick:()=>send({kind:'clear'})}),
      element('button',{text:t('看提示','Hint'),onclick:()=>{hintOpen=!hintOpen;render();}})
    ]));if(hintOpen)box.append(element('p',{class:'feedback',text:t('试试先把1号2×2板放在左上角。两块3×1板可以沿底部两行摆放；最后用竖着的2×1板补右下角。','Try piece 1 in the top-left corner. The two 3×1 pieces can run along the bottom two rows; a vertical 2×1 fills the lower-right corner.')}));
  } else if(config.kind==='budget'){
    box.append(element('h3',{text:t('把缺的一份补上','Fill the one-unit gap')}),element('p',{class:'budget-total',text:t('公用4份 · 炊柴2份 + 修缮3份 = 缺1份','Public funds 4 · Fuel 2 + Repairs 3 = Short by 1')}));
    const prepared=session.config();for(const plan of prepared.plans){const selected=state.selected===plan.id;box.append(element('button',{class:'plan',disabled:plan.allowed===false||busy,'aria-pressed':String(selected),onclick:()=>send({kind:'select',id:plan.id})},[element('strong',{text:text(plan.label)}),element('small',{text:text(plan.allowed===false?plan.locked:plan.detail)})]));}
    const chosen=prepared.plans.find(p=>p.id===state.selected);if(chosen){const meter=element('div',{class:'budget-meter'});for(let i=0;i<5;i++)meter.append(element('span',{class:i>=chosen.funds?'empty':''}));box.append(meter,element('p',{class:'budget-total',text:t(`可用${chosen.funds}份 / 支出${chosen.cost}份：收支平衡`,`Available ${chosen.funds} / Cost ${chosen.cost}: balanced`)}));}
    box.append(element('button',{class:'primary',text:t('确认安排，并兑现承诺 →','Commit to this plan →'),disabled:!chosen||busy,onclick:()=>send({kind:'confirm'})}),element('p',{class:'muted',text:t('以上为原创游戏单位，不是真实历史币值。','These are fictional game units, not historical prices.')}));
  }
}
function renderEnding(root){const ending=session.presentation.endings.find(e=>e.id===session.state.ending_id),v=session.variables();root.append(element('span',{class:'eyebrow ending-marker',text:t('故事结束','THE END')}),element('h2',{class:'end-title',text:text(ending.title)}),element('p',{text:text(ending.text)}));
  root.append(element('div',{class:'summary-row'},[element('span',{text:t('炊柴 / 修缮 / 公款余量','Fuel / Repairs / Public balance')}),element('strong',{text:`${v.fuel_payment} / ${v.repair_payment} / ${v.public_remaining}`})]));
  const details=[v.owned_error?t('你承认了报错。Kemal仍愿意帮你核对。','You admitted your mistake. Kemal is still willing to help.'):t('你把责任推给Kemal。他不再替你补充情况，Davud的同行邀请也未建立。','You blamed Kemal. He withdrew his help, and Davud’s travelling offer was not established.'),v.heard_davud?t('你听到了Davud作为受助者的完整说法。','You heard Davud’s full account as the beneficiary.'):t('Davud没有把旧事说全。这局只能保留你真正听到的部分。','Davud did not tell the full story. Only what you actually heard belongs in this account.'),v.privacy_consent?t('你先征求了他们的同意。','You asked permission before sharing their story.'):t('你先向别人讲了私事，再向他们解释，留下了新的隔阂。','You shared private details first and explained afterwards, creating new distance.'),v.mother_consulted?t('母亲参与了这次决定。','Meryem was included in this decision.'):t('母亲又一次被留在决定之外。','Meryem was left outside the decision again.'),v.handling_rework?t('工料曾送错，你返工后纠正了记录。','You corrected the supply records after rework.'):t('你一次分清了工料用途。','You separated the materials without rework.')];
  for(const line of details)root.append(element('p',{class:'choice-note',text:line}));root.append(element('p',{text:t('Murad II的归葬照常发生。石上的文字没有改，改变的是Yusuf怎样度过这一天。','Murad II’s burial proceeds as history records. The stone’s words do not change. Yusuf’s own day does.')}),element('button',{class:'primary',text:t('再走一次不同的路','Try another path'),onclick:restart}));
}
function openSource(number){
  const object=session.presentation.objects.find(o=>o.number===number);if(!object)return;stopWalker();try{session.recordBrowse(number);}catch(error){notify(error.message);}
  $('#notebook-dialog').close();const body=$('#source-body');body.replaceChildren();body.append(element('h2',{text:`${String(number).padStart(2,'0')} · ${object.historical_title}`}));
  const image=element('img',{src:object.media_path,alt:object.historical_title,onerror:()=>notify(t('来源图片加载失败；文字仍可阅读，请刷新后重试。','Source image failed to load. Text remains available; refresh to retry.'))});
  body.append(use3D?element('details',{},[element('summary',{text:t('查看来源图片','Source image')}),image]):image,element('p',{class:'caption',text:t(`II. Murat Külliyesi · PDF第${object.image_page}页 · ${object.image_role==='object_image'?'来源对象图':'来源文字截图'}`,`II. Murat Külliyesi · PDF page ${object.image_page} · ${object.image_role==='object_image'?'source image':'source text excerpt'}`)}),element('p',{text:text(session.presentation.sourceNotes[number])}),element('p',{class:'limit',text:locale==='zh'?object.scope_warning:text(session.presentation.sourceNotes[number])}));
  const details=element('details',{},[element('summary',{text:t('查看馆内完整说明与来源限制','Full museum snapshot and source limitations')}),element('pre',{text:object.content})]);body.append(details);
  if(session.current.requiredSources.includes(number)&&!session.state.ending_id){const recorded=session.entry().sources.includes(number),arrived=!use3D||cinematic?.canObserve(number)===true;if(use3D&&cinematic.readOnlyObservation(number))body.append(element('p',{class:'muted',text:t('此处无需走近，读完资料后可确认完成观察。','No approach is required here. Finish reading, then confirm the observation.')}));if(!arrived)body.append(element('p',{class:'muted',text:t('这项资料必须到现场阅读：先关闭此窗，双击目标点位并走近；到达后再打开资料。','This required source must be read at its location. Close this window, double-click the target, and approach it; then open the source again.')}));body.append(element('button',{class:'primary',text:recorded?t('✓ 本次观察已完成','✓ Observation completed'):arrived?t('读完并完成本次观察','Finish reading and record observation'):t('先走近，再完成观察','Approach before recording'),disabled:recorded||!arrived,onclick:()=>run(()=>{session.observeSource(number);$('#source-dialog').close();if(use3D&&session.nextSource()===null)openEncounter();})}));}
  if(use3D&&session.nextSource()===null&&!session.state.ending_id)body.append(element('button',{class:'primary',text:t('继续当前任务 →','Continue current task →'),onclick:()=>{$('#source-dialog').close();if(session.taskDone())openTask();else openEncounter();}}));
  if(!walking)body.append(element('button',{text:use3D?t('朝这里看','Look toward this object'):t('在全景中定位','Locate in panorama'),onclick:()=>{$('#story-panel').close();$('#source-dialog').close();cinematic.locate(number);}}));
  $('#source-dialog').showModal();render();
}
function openNotebook(){stopWalker();const list=$('#source-list');list.replaceChildren();for(const object of session.presentation.objects)list.append(element('button',{onclick:()=>cinematic.click(object.number),onkeydown:event=>{if(event.key==='Enter'){event.preventDefault();cinematic.key(object.number,event.shiftKey);}}},[element('strong',{text:`${session.notebook.includes(object.number)?'✓':'ⓘ'} ${String(object.number).padStart(2,'0')} · ${object.historical_title}`}),element('small',{text:text(session.presentation.sourceNotes[object.number])})]));$('#notebook-dialog').showModal();}
function download(raw,name){const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));const a=element('a',{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function restart(){if(!confirm(t('重开会替换本Demo的本机进度。需要保留时，请先导出存档。确认重开？','Start again and replace this demo’s local progress? Export first if you wish to keep it.')))return;try{localStorage.removeItem(session.key);location.reload();}catch(error){notify(t('无法清除本Demo存档：','Could not reset this demo: ')+error.message);}}
function bindControls(){
  dialogue=new DialoguePlayer({root:$('#dialogue'),onSpeaker:(name,action)=>cinematic?.setSpeaker(name,action),onError:error=>notify(error.message)});cinematic=new (use3D?Scene3DView:CinematicView)({session,inspect:openSource,openTask:openEncounter,notify,refresh:render,isTalking:()=>dialogue.active,closeDialogue:()=>dialogue.close(),guide:openGuide});
  $('#quest-title').onclick=()=>openTask();
  $('#close-task').onclick=()=>$('#story-panel').close();$('#story-panel').addEventListener('close',()=>dialogue?.resume());
  $('#locate-target').onclick=()=>{if(use3D&&session.nextSource()===null){if(session.taskDone())openTask();else openEncounter();}else cinematic.locate(use3D?session.nextSource():session.presentation.stageTargets[session.current.id]);};
  $('#notebook').onclick=openNotebook;$('#pause').onclick=()=>{session.paused=!session.paused;stopWalker();render();};$('#export').onclick=()=>download(session.serialize(),'murat-story-save.json');$('#restart').onclick=restart;$('#language').onclick=()=>{locale=locale==='zh'?'en':'zh';render();};$('#start').onclick=()=>{$('#welcome').close();try{session.persist();}catch(error){notify(error.message);}render();cinematic.startGuide?.();};
  for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>document.getElementById(button.dataset.close).close();
  addEventListener('keydown',event=>{if(restoring||busy||session.paused||$('#source-dialog').open||$('#notebook-dialog').open||$('#welcome').open)return;if($('#story-panel').open&&session.current.plugin.kind==='routing'&&!session.taskDone()&&['1','2','3'].includes(event.key)){const bin=session.current.plugin.bins[Number(event.key)-1];run(async()=>{const step=await session.dispatch({kind:'route',bin:bin.id});lastFeedback=step.message;});}});
}

async function loadJson(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error(`Cannot load ${url}`);return response.json();}
async function boot(){
  try{
    const[pkg,reference,presentation]=await Promise.all(['data/runtime.json','data/reference.json','data/presentation.json'].map(loadJson));
    validateNavigation(presentation);session=await GameSession.create(pkg,reference,presentation,localStorage);if(use3D)session.key='pastport:murat-story-demo:save:3d-v1';bindControls();let resumed=false;
    try{resumed=session.load();}catch(error){restoring=true;render();const panel=$('#task');panel.replaceChildren(element('div',{class:'task-box'},[element('h3',{text:'存档暂时无法载入'}),element('p',{text:error.message}),element('button',{text:'下载原存档',onclick:()=>download(localStorage.getItem(session.key)??'','murat-unread-save.json')}),element('button',{text:'重新开始本Demo',onclick:restart})]));$('#story-panel').showModal();return;}
    render();if(!resumed){$('#intro').textContent=text(presentation.intro);$('#welcome').showModal();}else{notify(t('已恢复上次进度。','Previous progress restored.'));if(session.shotState){cinematic.restorePending=true;if(cinematic.ready){cinematic.restorePending=false;cinematic.restore();}}}
  }catch(error){$('#story').replaceChildren(element('h2',{text:'Demo暂时无法打开'}),element('p',{text:error.message}));console.error(error);}
}
await boot();
