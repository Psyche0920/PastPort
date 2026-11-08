import {isInvestigation,validateInvestigationConfig,validateInvestigationState,reduceInvestigation} from './investigation.mjs';
import {gameplayCatalog} from './gameplay-catalog.mjs';
import {solveCoverage} from './coverage.mjs';
/** Deterministic local activities. No story state or storage access. */
export class ActivityError extends Error {}
const ensure = (condition, message) => { if (!condition) throw new ActivityError(message); };
const integer = n => Number.isSafeInteger(n) && n >= 0 && n < 10000;
const copy = value => structuredClone(value);
export class Activity {
  constructor(config) {
    ensure(config && (['question','routing','dialogue','tiling','budget'].includes(config.kind)||isInvestigation(config.kind)), 'Unknown activity');
    this.config = copy(config);
    if(isInvestigation(config.kind))validateInvestigationConfig(config);
    const entries=(items,label)=>{ensure(Array.isArray(items)&&items.length>0&&items.length<=128,`Invalid ${label}`);ensure(items.every(item=>item&&typeof item.id==='string'&&item.id.length>0)&&new Set(items.map(item=>item.id)).size===items.length,`Invalid ${label} identities`);};
    if(config.kind==='question'){entries(config.options,'question options');ensure(config.options.some(option=>option.correct===true),'Question has no accepted answer');}
    if(config.kind==='routing'){entries(config.cards,'routing cards');entries(config.bins,'routing bins');ensure(config.cards.every(card=>config.bins.some(bin=>bin.id===card.target)),'Routing target is missing');}
    if(config.kind==='dialogue')entries(config.items,'dialogue items');
    if(config.kind==='budget'){entries(config.plans,'budget plans');ensure([config.public,config.fuel,config.repair].every(integer)&&config.plans.every(plan=>integer(plan.funds)&&integer(plan.cost))&&config.plans.some(plan=>plan.funds>=plan.cost),'Invalid budget amounts');}
    if (config.kind === 'tiling') {
      ensure(Object.keys(config).every(key=>['kind','width','height','pieces','rotation_allowed','source_gate','failure_policy','exit_policy'].includes(key)),'Unexpected coverage requirements');
      ensure(config.rotation_allowed===undefined||typeof config.rotation_allowed==='boolean','Invalid rotation policy');
      ensure(config.failure_policy===undefined||config.failure_policy==='retry_without_story_progress','Unsupported failure policy');
      ensure(config.exit_policy===undefined||config.exit_policy==='preserve_progress','Unsupported exit policy');
      this.solution=solveCoverage(config);
      if(config.source_gate){
        entries(config.source_gate.options,'source choice options');
        ensure(config.source_gate.options.every(item=>item.text&&['en',item.text.tr?'tr':'zh'].every(locale=>typeof item.text[locale]==='string'&&item.text[locale].length>0)),'Source choice text is missing');
        ensure(config.source_gate.options.length<=gameplayCatalog.profiles.find(item=>item.kind==='tiling').max_items&&config.source_gate.options.some(item=>item.id===config.source_gate.target_claim_id),'Invalid source choice');
      }
    }
  }
  initialize() { return {version:2,termination:null,kind:this.config.kind,done:false,attempts:0,cursor:0,seen:[],placements:[],selected:null}; }
  validateState(state) {
    ensure(state && [1,2].includes(state.version) && state.kind === this.config.kind && typeof state.done === 'boolean', 'Incompatible activity save');
    ensure(Object.keys(state).sort().join(',') === (state.version===2?'attempts,cursor,done,kind,placements,seen,selected,termination,version':'attempts,cursor,done,kind,placements,seen,selected,version'), 'Unexpected activity fields');
    ensure(integer(state.attempts) && integer(state.cursor) && Array.isArray(state.seen) && Array.isArray(state.placements), 'Invalid activity state');
    ensure(state.seen.every(x=>typeof x==='string') && new Set(state.seen).size === state.seen.length, 'Invalid dialogue state');
    const c=this.config;
    if(state.version===2){ensure([null,'failed','exited'].includes(state.termination),'Invalid terminal result');ensure(!state.done||state.termination===null,'Completed activity cannot also terminate');ensure(state.termination!=='failed'||c.kind==='tiling','Unsupported failure result');}
    if(isInvestigation(c.kind))validateInvestigationState(c,state);
    if(c.kind==='routing') {ensure(state.cursor<=c.cards.length,'Invalid routing position');ensure(state.done===(state.cursor===c.cards.length),'Invalid routing result');}
    if(c.kind==='question') {ensure(state.selected===null||c.options.some(o=>o.id===state.selected),'Invalid answer');ensure(state.done===(c.options.find(o=>o.id===state.selected)?.correct===true),'Invalid question result');}
    if(c.kind==='dialogue') {ensure(state.seen.every(id=>c.items.some(i=>i.id===id)),'Unknown dialogue');ensure(state.done===(state.seen.length===c.items.length),'Incomplete dialogue result');}
    if(c.kind==='budget') {ensure(state.selected===null||c.plans.some(p=>p.id===state.selected),'Unknown resource plan');if(state.done)ensure(c.plans.some(p=>p.id===state.selected&&p.allowed!==false&&p.funds>=p.cost),'Unavailable resource plan');}
    if(c.kind==='tiling') {
      if(c.source_gate){ensure(state.selected===null||c.source_gate.options.some(item=>item.id===state.selected),'Unknown source selection');ensure(!state.done||state.selected===c.source_gate.target_claim_id,'Puzzle completed without source inference');}
      ensure(state.placements.length<=c.pieces.length,'Too many pieces');const ids=new Set(), cells=new Set();
      for(const p of state.placements) {
        ensure(p&&Object.keys(p).sort().join(',')==='id,rotated,x,y'&&integer(p.id)&&p.id<c.pieces.length&&!ids.has(p.id)&&typeof p.rotated==='boolean'&&(!p.rotated||c.rotation_allowed!==false)&&integer(p.x)&&integer(p.y),'Invalid placement');ids.add(p.id);
        const [w,h]=p.rotated?[...c.pieces[p.id]].reverse():c.pieces[p.id];ensure(p.x+w<=c.width&&p.y+h<=c.height,'Piece outside board');
        for(let x=p.x;x<p.x+w;x++)for(let y=p.y;y<p.y+h;y++){const key=`${x},${y}`;ensure(!cells.has(key),'Overlapping pieces');cells.add(key);}
      }
      ensure(state.done===(cells.size===c.width*c.height),'Invalid board completion');
    }
    return true;
  }
  reduce(state,command) {
    this.validateState(state);ensure(!state.done,'Activity already complete');ensure(command&&typeof command.kind==='string','Command required');
    const next={...copy(state),version:2,termination:state.termination??null},c=this.config;let message='';
    if(next.termination){
      ensure(command.kind===(next.termination==='exited'?'resume':'retry'),'Resume or retry is required');
      if(next.termination==='failed'){const reset=this.initialize();this.validateState(reset);return {state:reset,result:this.result(reset),message:'retry'};}
      next.termination=null;this.validateState(next);return {state:next,result:this.result(next),message:'resumed'};
    }
    if(command.kind==='exit'||c.kind==='tiling'&&command.kind==='give_up'){
      next.termination=command.kind==='give_up'?'failed':'exited';this.validateState(next);return {state:next,result:this.result(next),message:next.termination};
    }
    if(isInvestigation(c.kind)){message=reduceInvestigation(c,next,command);}
    else if(c.kind==='question') {
      ensure(command.kind==='answer','Expected answer');const option=c.options.find(o=>o.id===command.id);ensure(option,'Unknown answer');
      next.selected=option.id;next.done=option.correct===true;if(!next.done){next.attempts++;message=option.id;}
    } else if(c.kind==='routing') {
      ensure(command.kind==='route'&&c.bins.some(b=>b.id===command.bin),'Unknown destination');
      if(c.cards[next.cursor].target===command.bin)next.cursor++;else{next.attempts++;message='wrong-bin';}next.done=next.cursor===c.cards.length;
    } else if(c.kind==='dialogue') {
      ensure(command.kind==='read'&&c.items.some(i=>i.id===command.id),'Unknown conversation');if(!next.seen.includes(command.id))next.seen.push(command.id);next.done=next.seen.length===c.items.length;
    } else if(c.kind==='budget') {
      ensure(['select','confirm'].includes(command.kind),'Unknown budget command');
      if(command.kind==='select'){const plan=c.plans.find(p=>p.id===command.id);ensure(plan&&plan.allowed!==false,'Plan unavailable');next.selected=plan.id;}
      else {const plan=c.plans.find(p=>p.id===next.selected);ensure(plan&&plan.allowed!==false&&plan.funds>=plan.cost,'Budget is not balanced');next.done=true;}
    } else if(c.kind==='tiling') {
      if(command.kind==='evidence'){
        ensure(c.source_gate&&c.source_gate.options.some(item=>item.id===command.id),'Unknown evidence choice');
        next.selected=command.id;
        if(command.id!==c.source_gate.target_claim_id){next.termination='failed';next.attempts++;message='source_mismatch';}
      }else {
      ensure(!c.source_gate||next.selected===c.source_gate.target_claim_id,'Choose source evidence before arranging panels');
      if(command.kind==='undo')next.placements.pop();
      else if(command.kind==='clear')next.placements=[];
      else {
        ensure(command.kind==='place'&&integer(command.id)&&command.id<c.pieces.length&&integer(command.x)&&integer(command.y)&&typeof command.rotated==='boolean','Invalid board command');
        ensure(!next.placements.some(p=>p.id===command.id),'Piece already placed');
        next.placements.push({id:command.id,x:command.x,y:command.y,rotated:command.rotated});
      }
      next.done=next.placements.length===c.pieces.length;
      }
    }
    this.validateState(next);return {state:next,result:this.result(next),message};
  }
  result(state) {
    this.validateState(state);if(state.termination)return {status:state.termination,outcome:state.termination==='failed'?'retry':'resume',score:null};return {status:state.done?'completed':'running',outcome:state.done?(this.config.kind==='routing'?(state.attempts?'rework':'clean'):this.config.kind==='budget'?state.selected:'complete'):null,score:null};
  }
  serialize(state) {this.validateState(state);return JSON.stringify(state);}
  restore(snapshot) {ensure(typeof snapshot==='string'&&snapshot.length<=20000,'Activity save is too large');const state=JSON.parse(snapshot);this.validateState(state);return state;}
}
