/** Display-only localization. Never changes chapter IDs, decisions, events or saves. */
const normalize=value=>value.replace(/\s+/gu,' ').trim();
const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export function templateParts(value){
 const chunks=[],variables=[];let cursor=0;
 while(true){const start=value.indexOf('${',cursor);if(start<0){chunks.push(value.slice(cursor));break;}chunks.push(value.slice(cursor,start));let depth=1,quote=null,index=start+2;
  for(;index<value.length;index++){const ch=value[index];if(quote){if(ch==='\\')index++;else if(ch===quote)quote=null;continue;}if(['"',"'",'`'].includes(ch)){quote=ch;continue;}if(ch==='{')depth++;if(ch==='}'&&--depth===0)break;}
  if(depth!==0)return null;variables.push(value.slice(start+2,index));cursor=index+1;
 }return {chunks,variables};
}
export class DisplayLexicon {
 constructor(catalog){
  if(catalog.version!==1||!Array.isArray(catalog.entries))throw new TypeError('Unsupported display catalog');
  this.cache=new Map();this.characters=catalog.simplified_characters??{};this.maps={zh:new Map(),en:new Map(),tr:new Map()};this.templates=[];
  for(const entry of catalog.entries){
   if(!['zh','en','tr'].every(key=>typeof entry[key]==='string'&&entry[key].trim()))throw new TypeError('Incomplete display translation');
   const primary=templateParts(entry.en);
   for(const source of new Set([entry.original_zh,entry.zh,entry.en,entry.tr].filter(Boolean))){
    const key=normalize(source);if(!key.includes('${')){for(const locale of ['zh','en','tr'])this.maps[locale].set(key,entry[locale]);continue;}
    const parts=templateParts(key);if(!parts||!primary||parts.variables.length!==primary.variables.length||parts.chunks.join('').trim().length<2)continue;
    const targets=Object.fromEntries(['zh','en','tr'].map(locale=>[locale,templateParts(entry[locale])]));
    if(Object.values(targets).some(value=>!value||value.variables.length!==parts.variables.length))continue;
    this.templates.push({prefix:parts.chunks[0],suffix:parts.chunks.at(-1),pattern:new RegExp('^'+parts.chunks.map(escape).join('(.*?)')+'$','u'),targets});
   }
  }
  this.fragments=Object.fromEntries(['zh','en','tr'].map(locale=>[locale,new RegExp([...this.maps[locale].keys()].filter(key=>key.length>=3||(key.length>=2&&/^[\p{Script=Han}]+$/u.test(key))).sort((a,b)=>b.length-a.length).map(escape).join('|'),'gu')]));
 }
 simplify(value){return [...value].map(character=>this.characters[character]??character).join('');}
 translate(value,locale,depth=0){
  if(!Object.hasOwn(this.maps,locale))throw new RangeError('Unsupported display language');
  if(typeof value!=='string'||!value.trim())return value;
  const cacheKey=locale+'\0'+value;if(this.cache.has(cacheKey))return this.cache.get(cacheKey);
  const remember=result=>{if(this.cache.size>=4096)this.cache.clear();this.cache.set(cacheKey,result);return result;};
  const input=normalize(value),leading=value.match(/^\s*/u)[0],trailing=value.match(/\s*$/u)[0];
  const direct=this.maps[locale].get(input);if(direct!==undefined)return remember(leading+direct+trailing);
  if(depth<3)for(const template of this.templates){if(!input.startsWith(template.prefix)||!input.endsWith(template.suffix))continue;const match=input.match(template.pattern);if(match){const target=template.targets[locale];let result=target.chunks[0];for(let i=0;i<target.variables.length;i++)result+=this.translate(match[i+1],locale,depth+1)+target.chunks[i+1];return remember(leading+result+trailing);}}
  const output=value.replace(this.fragments[locale],(match,index,whole)=>{
   if(/[A-Za-z]/.test(match[0])&&/[A-Za-z]/.test(whole[index-1]??''))return match;
   if(/[A-Za-z]/.test(match.at(-1))&&/[A-Za-z]/.test(whole[index+match.length]??''))return match;
   return this.maps[locale].get(match);
  });return remember(locale==='zh'?this.simplify(output):output);
 }
}
/** Mount display translation only in same-origin game frames; release listeners on teardown. */
export class SameOriginFrameLocalizations {
 constructor(doc,mount){this.doc=doc;this.mount=mount;this.frames=new Map();this.locale='zh';}
 sync(locale){
  this.locale=locale;const live=new Set(this.doc.querySelectorAll('iframe'));
  for(const [frame,record] of this.frames)if(!live.has(frame)){frame.removeEventListener('load',record.load);record.display?.close();this.frames.delete(frame);}
  for(const frame of live){
   let record=this.frames.get(frame);
   if(!record){record={document:null,display:null,load:()=>this.sync(this.locale)};this.frames.set(frame,record);frame.addEventListener('load',record.load);}
   let child;try{child=frame.contentDocument;}catch(error){if(error.name!=='SecurityError')throw error;continue;}
   if(!child?.body||child.URL==='about:blank'){record.display?.close();record.display=null;record.document=null;continue;}
   if(record.document!==child){record.display?.close();record.document=child;record.display=this.mount(child,locale);}
   if(record.display.locale!==locale)record.display.setLocale(locale);
  }
 }
 close(){for(const [frame,record]of this.frames){frame.removeEventListener('load',record.load);record.display?.close();}this.frames.clear();}
}
export function installDisplayLocalization(catalog,{doc=document,storage=localStorage,initialLocale=null,showPicker=true,includeFrames=false,translateCanvas=false}={}){
 const view=doc.defaultView;const lexicon=new DisplayLexicon(catalog);let saved=null;try{saved=storage.getItem('pastport:game-language');}catch(error){console.warn('language_preference_not_read',error.name);}
 let locale=['zh','en','tr'].includes(initialLocale)?initialLocale:['zh','en','tr'].includes(saved)?saved:'zh';
 const originals=new WeakMap();let rendering=false;
 const frames=includeFrames?new SameOriginFrameLocalizations(doc,(child,value)=>installDisplayLocalization(catalog,{doc:child,storage,initialLocale:value,showPicker:false,translateCanvas})):null;
 const canvasPrototype=translateCanvas?view.CanvasRenderingContext2D?.prototype:null;
 const nativeFill=canvasPrototype?.fillText;
 const translatedFill=nativeFill?function(value,...args){return nativeFill.call(this,typeof value==='string'?lexicon.translate(value,locale):value,...args);}:null;
 if(translatedFill)canvasPrototype.fillText=translatedFill;
 const announce=()=>view.dispatchEvent(new view.CustomEvent('pastport:display-language',{detail:{locale}}));
 function rewrite(node,key,read,write,transform=value=>lexicon.translate(value,locale)){const current=read();if(typeof current!=='string')return;const fields=originals.get(node)??{};const old=fields[key];const original=old&&current===old.rendered?old.original:current;const rendered=transform(original);fields[key]={original,rendered};originals.set(node,fields);if(current!==rendered)write(rendered);}
 function picker(){const select=doc.createElement('select');select.className='pastport-language';select.dataset.noI18n='';for(const [value,label]of [['zh','简体中文'],['en','English'],['tr','Türkçe']]){const option=doc.createElement('option');option.value=value;option.textContent=label;select.append(option);}select.onchange=()=>{locale=select.value;try{storage.setItem('pastport:game-language',locale);}catch(error){console.warn('language_preference_not_saved',error.name);}const url=new URL(view.location.href);url.searchParams.set('lang',locale);view.history.replaceState(null,'',url);render();announce();if(view.parent!==view&&doc.referrer){let parentOrigin;try{parentOrigin=new URL(doc.referrer).origin;}catch{return;}view.parent.postMessage({type:'pastport:language-change',run:new URL(view.location.href).searchParams.get('passportRun'),locale},parentOrigin);}};return select;}
 const style=doc.createElement('style');style.textContent='.pastport-language{font:14px/1.4 system-ui,sans-serif;padding:8px 10px;border-radius:8px;border:1px solid #c9b37e;background:#fff7e3;color:#253d35;max-width:145px;pointer-events:auto}.pastport-language-main{position:fixed;right:14px;top:12px;z-index:9000}dialog>.pastport-language{display:block;margin:0 0 14px auto}#language,#welcome-language{display:none!important}';doc.head.append(style);
 const main=showPicker?picker():null;if(main){main.classList.add('pastport-language-main');doc.body.append(main);}
 function render(){if(rendering)return;rendering=true;try{
  if(showPicker)for(const dialog of doc.querySelectorAll('dialog[open]'))if(!dialog.querySelector('.pastport-language'))dialog.prepend(picker());
  const documentLocale=locale==='zh'?'zh-CN':locale;if(doc.documentElement.lang!==documentLocale)doc.documentElement.lang=documentLocale;
  for(const select of doc.querySelectorAll('.pastport-language')){select.value=locale;const label={zh:'游戏语言',en:'Game language',tr:'Oyun dili'}[locale];if(select.getAttribute('aria-label')!==label)select.setAttribute('aria-label',label);}
  const walker=doc.createTreeWalker(doc.body,4);while(walker.nextNode()){const node=walker.currentNode;if(!node.parentElement?.closest('script,style,textarea,input,code,pre,[data-no-i18n]'))rewrite(node,'text',()=>node.data,value=>{node.data=value;});}
  for(const node of doc.querySelectorAll('[aria-label],[title],[alt],[placeholder],[data-label]' )){if(node.closest('[data-no-i18n]'))continue;for(const key of ['aria-label','title','alt','placeholder','data-label'])if(node.hasAttribute(key))rewrite(node,key,()=>node.getAttribute(key),value=>node.setAttribute(key,value));}
  for(const image of doc.querySelectorAll('img[src]'))rewrite(image,'src',()=>image.getAttribute('src'),value=>image.setAttribute('src',value),value=>{const url=new URL(value,doc.baseURI);if(url.origin!==view.location.origin)return value;const target=catalog.display_assets?.[url.pathname.slice(1)]?.[locale];return target?'/'+target:value;});
  rewrite(doc,'title',()=>doc.title,value=>{doc.title=value;});frames?.sync(locale);
 }finally{rendering=false;}}
 const message=event=>{if(event.source!==view.parent||event.data?.type!=='pastport:language'||!['zh','en','tr'].includes(event.data.locale))return;let parentOrigin;try{parentOrigin=new URL(doc.referrer).origin;}catch{return;}if(event.origin!==parentOrigin)return;const changed=locale!==event.data.locale;locale=event.data.locale;render();if(changed)announce();};
 view.addEventListener('message',message);
 const observer=new view.MutationObserver(render);observer.observe(doc.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','title','alt','placeholder','data-label','open','src','lang']});render();
 return {lexicon,get locale(){return locale;},setLocale(value){if(!['zh','en','tr'].includes(value))throw new RangeError('Unsupported display language');const changed=locale!==value;locale=value;render();if(changed)announce();},close(){observer.disconnect();frames?.close();if(translatedFill&&canvasPrototype.fillText===translatedFill)canvasPrototype.fillText=nativeFill;view.removeEventListener('message',message);for(const select of doc.querySelectorAll('.pastport-language'))select.remove();style.remove();}};
}
