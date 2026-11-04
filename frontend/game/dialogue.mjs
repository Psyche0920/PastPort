export function formatCaseFile(text){
 return text.replace(/【遊戲虛構([^】]+)】/g,'$1\n\n').replace(/\[Fictional ([^\]]+)\]/g,(_,title)=>title.charAt(0).toUpperCase()+title.slice(1)+'\n\n').replace(/【通知 B】/g,'\n\n通知 B\n').replace(/\[Notice B\]/g,'\n\nNotice B\n').replace(/([。！？])\s*/g,'$1\n\n').replace(/\. +(?=[A-Z])/g,'.\n\n').trim();
}
/** Adapted from UI trial adventure.mjs speak/renderLine: one speaker, one line, Continue. */
export class DialoguePlayer {
  constructor({root,onSpeaker=()=>{},onError=()=>{},getLocale=()=>'zh'}){this.root=root;this.onSpeaker=onSpeaker;this.onError=onError;this.getLocale=getLocale;this.conversation=null;this.busy=false;}
  get active(){return this.conversation!==null;}
  open(lines,{acknowledge=async()=>{},done=()=>{},startIndex=0}={}){this.suspended=false;this.conversation={lines,index:Math.max(0,Math.min(startIndex,lines.length-1)),acknowledge,done};this.renderLine();}
  suspend(){if(this.conversation){this.suspended=true;this.root.hidden=true;}}
  resume(){if(this.suspended){this.suspended=false;if(this.conversation)this.renderLine();}}
  close(){this.suspended=false;this.root.hidden=true;this.conversation=null;this.onSpeaker(null);}
  renderLine(){
    const c=this.conversation;if(!c)return;const line=c.lines[c.index];if(!line){const done=c.done;this.close();done();return;}
    this.root.hidden=false;this.root.classList.toggle('is-case-file',line.speaker==='archive');this.root.replaceChildren();this.onSpeaker(line.speaker,line.action??null);
    const portrait=document.createElement('div');portrait.className='portrait';portrait.style.setProperty('--portrait-x',line.row===0?'-46px':'-34px');const sprite=document.createElement('div');sprite.className='sprite';sprite.style.backgroundPosition=`${line.frame*100/3}% ${line.row}%`;portrait.append(sprite);
    const speaker=document.createElement('div');speaker.className='speaker';speaker.textContent=line.speakerLabel??line.speaker;const body=document.createElement('div');body.className='dialogue-text';body.textContent=line.speaker==='archive'?formatCaseFile(line.text):line.text;
    const actions=document.createElement('div');actions.className='dialogue-actions';const previous=document.createElement('button');previous.textContent=this.getLocale()==='en'?'← Previous line':'← 上一句';previous.disabled=c.index===0||this.busy;previous.onclick=()=>{if(this.busy)return;c.index--;this.renderLine();};
    const next=document.createElement('button');next.textContent=this.getLocale()==='en'?(line.commit?'Confirm & continue →':'Continue →'):(line.commit?'確認並繼續 →':'繼續 →');next.disabled=this.busy;next.onclick=async()=>{if(this.busy)return;this.busy=true;next.disabled=true;try{await c.acknowledge(line);if(this.conversation===c){c.index++;this.busy=false;this.renderLine();}}catch(error){this.onError(error);this.busy=false;this.renderLine();}};
    const close=document.createElement('button');close.className='dialogue-close';close.textContent=this.getLocale()==='en'?'Close & explore':'收起，探索房間';close.onclick=()=>{if(!this.busy)this.close();};if(c.index>0)actions.append(previous);actions.append(next);this.root.append(portrait,speaker,body,close,actions);
  }
}
export const openingLines={
  s01:[{speaker:'İlyas',text:'你父亲以前也在这里做事？'},{speaker:'Yusuf',text:'他叫Hasan，是个木工。我母亲Meryem住在附近，只说他后来靠木工过活，没提过这里的事。'},{speaker:'İlyas',text:'Hasan？我听人说，他拿走过施食所的柴。'},{speaker:'Davud',action:'look-up',text:'你亲眼看见的？'},{speaker:'İlyas',text:'没有，听别人说的。'},{speaker:'Davud',text:'那就别急着说他偷东西。'},{speaker:'Yusuf',text:'母亲从没提过这件事。Davud却像是知道。'}],
  s02:[{speaker:'Salih',text:'木料到了没有？'},{speaker:'Yusuf',text:'到了。……等一下，到的是修缮用木，还是厨房要烧的柴？'},{speaker:'Salih',text:'先把两项工作分清。今天的饭还等着做。'}],
  s03:[{speaker:'Kemal',text:'学生房里不是也有炉火？先把做饭的活挪过去？'},{speaker:'Yusuf',text:'我先看看那些房间到底能做什么。这回不能又含糊答应。'}],
  s05:[{speaker:'Davud',text:'旧事说完，今天的屋面还得护住。板料有限，你帮我摆一摆。'},{speaker:'Meryem',text:'还有家里的备用钱。你要怎么用，总该先和我说清。'}],
  s06:[{speaker:'Salih',text:'公用的钱有四份。炊柴要两份，修缮要三份，还差一份。'},{speaker:'Yusuf',text:'这回不能只说“到了”。我选怎么补，就得把后面的事做完。'}]
};
/** Dialogue-only copy corrections do not alter rules or invalidate saved choices. */
export const spokenCopy={
  s04b:{mother:{
    zh:'后来是我拿家里的应急钱买柴补上的。Hasan告诉我，他把柴送去Davud家取暖。我没亲眼看见他拿柴。',
    en:'I used our emergency savings to replace the firewood. Hasan told me he had taken it to keep Davud’s family warm. I did not see him take it.'
  }}
};
