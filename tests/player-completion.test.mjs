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
  const events=new Map(),messages=[];let changed=()=>{},ending=false;
  const parent={postMessage:(value,origin)=>messages.push({value,origin})};
  const window={parent,addEventListener:(name,listener)=>events.set(name,listener)};
  const document={documentElement:{},querySelector:()=>ending?{}:null};
  class MutationObserver {constructor(callback){changed=callback;}observe(){}}
  const html=completionBootstrap({selector:'#panel[open] .ending-grid',saveKeys:['legacy']},'http://127.0.0.1:18856');
  runInNewContext(html.slice(8,-9),{URL,location:{href:`http://game.local/?passportRun=issued-run&passportScope=${scope}`},Storage,localStorage,window,document,MutationObserver});
  return {messages,localStorage,events,changed:()=>changed(),finish:()=>{ending=true;changed();}};
}
test('opening, observing and incomplete interactions never emit completion; an ending emits once',()=>{
  const game=fixture();game.changed();game.changed();assert.equal(game.messages.length,0);
  game.finish();assert.equal(game.messages.length,1);
  assert.equal(game.messages[0].value.type,'pastport:ending');
  assert.equal(game.messages[0].value.run,'issued-run');
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
  notify({detail:null});notify({detail:{}});notify({detail:{endingId:''}});
  assert.equal(game.messages.length,0);notify({detail:{endingId:'complete'}});assert.equal(game.messages.length,1);
  game.finish();assert.equal(game.messages.length,1);
});
