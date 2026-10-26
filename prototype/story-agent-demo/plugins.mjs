/** Deterministic local activities. No story state or storage access. */
export class ActivityError extends Error {}
const ensure = (condition, message) => { if (!condition) throw new ActivityError(message); };
const integer = n => Number.isSafeInteger(n) && n >= 0 && n < 10000;
const copy = value => structuredClone(value);
export class Activity {
  constructor(config) {
    ensure(config && ['question','routing','dialogue','tiling','budget'].includes(config.kind), 'Unknown activity');
    this.config = copy(config);
    if (config.kind === 'tiling') {
      ensure(config.width === 4 && config.height === 4 && config.pieces.length === 6, 'Unsupported board');
      ensure(config.pieces.reduce((sum,[w,h])=>sum+w*h,0) === 16, 'Pieces do not cover board');
    }
  }
  initialize() { return {version:1,kind:this.config.kind,done:false,attempts:0,cursor:0,seen:[],placements:[],selected:null}; }
  validateState(state) {
    ensure(state && state.version === 1 && state.kind === this.config.kind && typeof state.done === 'boolean', 'Incompatible activity save');
    ensure(Object.keys(state).sort().join(',') === 'attempts,cursor,done,kind,placements,seen,selected,version', 'Unexpected activity fields');
    ensure(integer(state.attempts) && integer(state.cursor) && Array.isArray(state.seen) && Array.isArray(state.placements), 'Invalid activity state');
    ensure(state.seen.every(x=>typeof x==='string') && new Set(state.seen).size === state.seen.length, 'Invalid dialogue state');
    const c=this.config;
    if(c.kind==='routing') {ensure(state.cursor<=c.cards.length,'Invalid routing position');ensure(state.done===(state.cursor===c.cards.length),'Invalid routing result');}
    if(c.kind==='question') {ensure(state.selected===null||c.options.some(o=>o.id===state.selected),'Invalid answer');ensure(state.done===(c.options.find(o=>o.id===state.selected)?.correct===true),'Invalid question result');}
    if(c.kind==='dialogue') {ensure(state.seen.every(id=>c.items.some(i=>i.id===id)),'Unknown dialogue');ensure(state.done===(state.seen.length===c.items.length),'Incomplete dialogue result');}
    if(c.kind==='budget') {ensure(state.selected===null||c.plans.some(p=>p.id===state.selected),'Unknown resource plan');if(state.done)ensure(c.plans.some(p=>p.id===state.selected&&p.allowed!==false&&p.funds>=p.cost),'Unavailable resource plan');}
    if(c.kind==='tiling') {
      ensure(state.placements.length<=c.pieces.length,'Too many pieces');const ids=new Set(), cells=new Set();
      for(const p of state.placements) {
        ensure(p&&Object.keys(p).sort().join(',')==='id,rotated,x,y'&&integer(p.id)&&p.id<c.pieces.length&&!ids.has(p.id)&&typeof p.rotated==='boolean'&&integer(p.x)&&integer(p.y),'Invalid placement');ids.add(p.id);
        const [w,h]=p.rotated?[...c.pieces[p.id]].reverse():c.pieces[p.id];ensure(p.x+w<=c.width&&p.y+h<=c.height,'Piece outside board');
        for(let x=p.x;x<p.x+w;x++)for(let y=p.y;y<p.y+h;y++){const key=`${x},${y}`;ensure(!cells.has(key),'Overlapping pieces');cells.add(key);}
      }
      ensure(state.done===(cells.size===16),'Invalid board completion');
    }
    return true;
  }
  reduce(state,command) {
    this.validateState(state);ensure(!state.done,'Activity already complete');ensure(command&&typeof command.kind==='string','Command required');
    const next=copy(state),c=this.config;let message='';
    if(c.kind==='question') {
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
      if(command.kind==='undo')next.placements.pop();
      else if(command.kind==='clear')next.placements=[];
      else {
        ensure(command.kind==='place'&&integer(command.id)&&command.id<c.pieces.length&&integer(command.x)&&integer(command.y)&&typeof command.rotated==='boolean','Invalid board command');
        ensure(!next.placements.some(p=>p.id===command.id),'Piece already placed');
        next.placements.push({id:command.id,x:command.x,y:command.y,rotated:command.rotated});
      }
      next.done=next.placements.length===c.pieces.length;
    }
    this.validateState(next);return {state:next,result:this.result(next),message};
  }
  result(state) {
    this.validateState(state);return {status:state.done?'completed':'running',outcome:state.done?(this.config.kind==='routing'?(state.attempts?'rework':'clean'):this.config.kind==='budget'?state.selected:'complete'):null,score:null};
  }
  serialize(state) {this.validateState(state);return JSON.stringify(state);}
  restore(snapshot) {ensure(typeof snapshot==='string'&&snapshot.length<=20000,'Activity save is too large');const state=JSON.parse(snapshot);this.validateState(state);return state;}
}
