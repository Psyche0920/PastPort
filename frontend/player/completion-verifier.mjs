import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {GameSession} from '../game/session.mjs';
import {EffectEvaluator} from '../../src/pastport/player/rules.mjs';

export class CompletionRejected extends Error {
  constructor(message='This run has not reached a verified ending.', options) {
    super(message,options);this.name='CompletionRejected';
  }
}
export function hasEndingSave(entries) {
  return Object.values(entries).some(raw=>{
    try {return typeof JSON.parse(raw)?.engine?.ending_id==='string';}
    catch {return false;}
  });
}
export function hasUnfinishedSave(entries) {
  return Object.values(entries).some(raw=>{
    try {const snapshot=JSON.parse(raw);return snapshot?.version===2&&snapshot.engine?.ending_id===null;}
    catch {return false;}
  });
}
/** Checks saved progress with the trusted shared engine; imported scripts are never executed. */
export class GameSessionCompletionVerifier {
  constructor(template) {this.template=template;}
  static async load(root, saveKey) {
    try {
      const [runtime,reference,presentation]=await Promise.all(['runtime','reference','presentation'].map(async name=>JSON.parse(await readFile(join(root,'data',name+'.json'),'utf8'))));
      const template=await GameSession.create(runtime,reference,presentation);
      if(saveKey)template.key=saveKey;
      return new GameSessionCompletionVerifier(template);
    } catch(cause) {throw new CompletionRejected('This game cannot provide a verified completion record.',{cause});}
  }
  verify(entries,endingId) {
    const template=this.template,raw=entries[template.key];
    if(typeof raw!=='string')throw new CompletionRejected();
    const session=new GameSession(template.context,template.presentation,template.gameplayPlan,template.identity,null);
    try {
      session.restore(raw);
      const state=session.state,game=session.context.game;
      if(!endingId||state.ending_id!==endingId)throw new CompletionRejected();
      // A valid ending alone cannot stand in for completing the route's required tasks and choices.
      const visited=new Set(),pending=[game.initial_state.current_scene_id];
      let reached=false;
      while(pending.length){
        const id=pending.shift();if(visited.has(id))continue;visited.add(id);
        const scene=session.context.scene(id);
        if(!state.unlocked_scene_ids.includes(id)||!scene.required_task_ids.every(task=>state.completed_task_ids.includes(task)))continue;
        if(scene.decision_id&&!state.decisions.some(choice=>choice.decision_id===scene.decision_id))continue;
        if(id===state.current_scene_id){reached=true;break;}
        pending.push(...scene.next_scene_ids);
      }
      if(!reached)throw new CompletionRejected();
      const effects=new EffectEvaluator(session.context);
      const resolved=game.rules.some(rule=>state.applied_rule_keys.includes(rule.once_key)&&rule.effects.some(effect=>effect.kind==='resolve_ending'&&effects.evaluate(state,effect).state.ending_id===endingId));
      if(!resolved)throw new CompletionRejected();
      return endingId;
    } catch(cause) {
      if(cause instanceof CompletionRejected)throw cause;
      throw new CompletionRejected('This run has not reached a verified ending.',{cause});
    }
  }
}
