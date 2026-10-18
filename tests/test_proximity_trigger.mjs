import test from 'node:test';
import assert from 'node:assert/strict';
import {ProximityTriggers} from '../prototype/proximity-trigger.mjs';
import {WalkMesh,Walker} from '../prototype/walkmesh.mjs';

const npc={id:'npc',action:'talk',approach:[50,90]};

test('Walking into a zone triggers once without clicking or pressing an interaction key',()=>{
  const triggers=new ProximityTriggers();
  const walker=new Walker(new WalkMesh([[0,0],[100,0],[100,100],[0,100]]),[20,90]);
  walker.goTo([50,90]);
  let fired=0;
  for(let frame=0;frame<200;frame++){
    walker.tick(.016);
    if(triggers.poll(walker.position,[npc]))fired++;
  }
  assert.equal(fired,1);
});

test('Standing still or jittering near a closed dialogue cannot reopen it',()=>{
  const triggers=new ProximityTriggers();
  assert.equal(triggers.poll([50,90],[npc]),npc);
  for(const position of [[50,90],[54,90],[55,90],[57,90],[54,90],[50,90]]) assert.equal(triggers.poll(position,[npc]),null);
  assert.equal(triggers.poll([60,90],[npc]),null);
  assert.equal(triggers.poll([50,90],[npc]),npc,'Leaving the release radius rearms the encounter');
});

test('Overlapping targets consume their entries together and only the nearest opens',()=>{
  const triggers=new ProximityTriggers(), other={id:'clue',action:'inspect',approach:[53,90]};
  assert.equal(triggers.poll([50,90],[other,npc]),npc);
  assert.equal(triggers.poll([52,90],[other,npc]),null);
});

test('Locked or completed interactions are skipped and do not auto-fire when unlocked in place',()=>{
  const triggers=new ProximityTriggers(),exit={id:'exit',action:'advance',approach:[50,90]};
  assert.equal(triggers.poll([50,90],[exit],()=>false),null);
  assert.equal(triggers.poll([50,90],[exit],()=>true),null);
  triggers.poll([60,90],[exit]);
  assert.equal(triggers.poll([50,90],[exit],()=>true),exit);
});

test('Manual interactions and saved spawn positions suppress immediate automatic repeats',()=>{
  const triggers=new ProximityTriggers();
  triggers.suppress([50,90],[npc]);
  assert.equal(triggers.poll([50,90],[npc]),null);
  triggers.poll([60,90],[npc]);
  assert.equal(triggers.poll([50,90],[npc]),npc);
});

test('An object across blocked geometry cannot trigger despite screen proximity',()=>{
  const mesh=new WalkMesh([[0,0],[100,0],[100,100],[0,100]],[[[48,80],[52,80],[52,100],[48,100]]]);
  const triggers=new ProximityTriggers(140,180),target={id:'across-wall',approach:[54,90]};
  assert.equal(triggers.poll([46,90],[target],object=>mesh.clear([46,90],object.approach)),null);
});
