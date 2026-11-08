import test from 'node:test';
import assert from 'node:assert/strict';
import {runInNewContext} from 'node:vm';
import {completionBootstrap} from '../tools/game-package/player-completion.mjs';

function fixture(scope='a'.repeat(64)) {
  class Storage {
    constructor(){this.entries=new Map();}
    getItem(key){return this.entries.get(String(key))??null;}
    setItem(key,value){this.entries.set(String(key),String(value));}
    removeItem(key){this.entries.delete(String(key));}
  }
  const localStorage=new Storage();localStorage.setItem('legacy','unbound-old-save');
  const events=new Map(),posted=[];let changed=()=>{},ending=false;
  const parent={postMessage:(value,origin)=>posted.push({value,origin})};
  const window={parent,addEventListener:(name,listener)=>events.set(name,listener),removeEventListener:name=>events.delete(name)};
  const held=[];
  const document={documentElement:{},readyState:'complete',querySelector:()=>ending?{}:null,
    querySelectorAll:()=>held.splice(0),createElement:()=>({attributes:[],setAttribute(){},})};
  const timers=[];
  class MutationObserver {constructor(callback){changed=callback;}observe(){}}
  const html=completionBootstrap({selector:'#panel[open] .ending-grid',saveKeys:['legacy']},'http://127.0.0.1:18856');
  runInNewContext(html.slice(8,-9),{URL,location:{href:`http://game.local/?passportRun=issued-run&passportScope=${scope}`},Storage,localStorage,window,document,MutationObserver,
    setTimeout:callback=>timers.push(callback),clearTimeout:()=>timers.splice(0)});
  const messages={get length(){return posted.filter(m=>m.value.type==='pastport:ending').length;},
    0:undefined};
  Object.defineProperty(messages,0,{get:()=>posted.find(m=>m.value.type==='pastport:ending')});
  return {messages,posted,parent,held,timers,localStorage,events,changed:()=>changed(),finish:()=>{ending=true;changed();}};
}
test('opening, observing and incomplete interactions never emit completion; an ending emits once',()=>{
  const game=fixture();game.changed();game.changed();assert.equal(game.messages.length,0);
  game.finish();assert.equal(game.messages.length,1);
  assert.equal(game.messages[0].value.type,'pastport:ending');
  assert.equal(game.messages[0].value.run,'issued-run');
  assert.equal(game.messages[0].value.endingId,'legacy-ending');
  assert.equal(game.messages[0].origin,'http://127.0.0.1:18856');
  game.finish();game.changed();assert.equal(game.messages.length,1);
});
test('legacy local saves are account-scoped and old unbound saves are retained',()=>{
  const game=fixture();assert.equal(game.localStorage.getItem('legacy'),null);
  game.localStorage.setItem('legacy','this-account-progress');
  assert.equal(game.localStorage.getItem('legacy'),'this-account-progress');
  assert.equal(game.localStorage.entries.get('legacy'),'unbound-old-save');
  assert.equal(game.localStorage.entries.get('pastport:account:'+'a'.repeat(64)+':legacy'),'this-account-progress');
});
test('new games can use the standard completion event; incomplete events cannot stamp',()=>{
  const game=fixture();const notify=game.events.get('pastport:completed');
  notify({detail:null});notify({detail:{}});notify({detail:{endingId:''}});notify({detail:{endingId:'   '}});
  assert.equal(game.messages.length,0);notify({detail:{endingId:'complete'}});assert.equal(game.messages.length,1);
  assert.equal(game.messages[0].value.endingId,'complete');
  game.finish();assert.equal(game.messages.length,1);
});

test('legacy account saves hydrate before the original modules start and mirror each write',()=>{
  const game=fixture();
  const started=[];game.held.push({attributes:[{name:'type',value:'pastport/deferred-module'},{name:'src',value:'adventure.mjs'}],textContent:'',replaceWith:value=>started.push(value)});
  assert.deepEqual(game.posted.map(m=>m.value.type),['pastport:save-ready']);
  const hydrate=game.events.get('message');
  hydrate({source:{},origin:'http://127.0.0.1:18856',data:{type:'pastport:save-state',run:'issued-run',entries:{legacy:'from-server'}}});
  assert.equal(started.length,0,'messages from another window are ignored');
  hydrate({source:game.parent,origin:'http://evil.example',data:{type:'pastport:save-state',run:'issued-run',entries:{legacy:'x'}}});
  hydrate({source:game.parent,origin:'http://127.0.0.1:18856',data:{type:'pastport:save-state',run:'issued-run',entries:{legacy:'from-server'}}});
  assert.equal(started.length,1);assert.equal(started[0].type,'module');
  assert.equal(game.localStorage.getItem('legacy'),'from-server');
  game.localStorage.setItem('legacy','next');
  assert.equal(JSON.stringify(game.posted.at(-1).value),JSON.stringify({type:'pastport:save-change',run:'issued-run',key:'legacy',value:'next'}));
  game.localStorage.setItem('unrelated','x');
  assert.equal(game.posted.at(-1).value.key,'legacy');
});
test('a missing platform answer reports a save error instead of starting with empty progress',()=>{
  const game=fixture();game.timers[0]();
  assert.equal(game.posted.at(-1).value.type,'pastport:save-error');
});
