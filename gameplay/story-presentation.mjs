/** Project validated opening-known copy; never infer introductions from hidden goals. */
export function storyPresentation(draft,tasks,fallback){
  const game=draft.package.game,tables=new Map(game.locales.map(table=>[table.locale,new Map(table.entries.map(e=>[e.key,e.text]))]));
  const keys=new Set([...tables.values()].flatMap(table=>[...table.keys()]));
  const prefix='presentation.';
  if(!keys.has(prefix+'opening_v1'))return fallback;
  const fail=message=>{throw new Error('STORY_OPENING_INVALID: '+message);};
  const read=key=>{const result={};for(const locale of ['zh','en']){const value=tables.get(locale)?.get(key);if(typeof value!=='string'||!value.trim())fail('Missing bilingual '+key);result[locale]=value;}return result;};
  const version=read(prefix+'opening_v1');if(version.zh!=='opening-context/1'||version.en!=='opening-context/1')fail('Unsupported opening profile');
  const title=read(prefix+'title'),setting=read(prefix+'setting'),situation=read(prefix+'situation'),role=read(prefix+'player_role'),question=read(prefix+'question');
  const hero=game.characters?.find(person=>person.character_id===game.protagonist);
  if(!hero)fail('Missing protagonist');
  const speakerNames={[hero.character_id]:read(hero.name_key)},characterProfiles=[{id:hero.character_id,introduction:role}];
  const people=[...new Set([...keys].filter(key=>key.startsWith(prefix+'person.')).map(key=>key.split('.')[2]))].sort((a,b)=>Number(a)-Number(b));
  if(people.length>10||people.some((id,index)=>id!==String(index+1)))fail('Invalid person sequence');
  for(const index of people){const id='presentation-person-'+index;if(game.characters.some(person=>person.character_id===id))fail('Display identity collision');speakerNames[id]=read(prefix+'person.'+index+'.name');characterProfiles.push({id,introduction:read(prefix+'person.'+index+'.introduction')});}
  const assets=new Set(tasks.map(task=>'object-'+task.asset_object_number));
  const stations=new Set([...keys].filter(key=>key.startsWith(prefix+'station.')).map(key=>key.split('.')[2]));
  if(assets.size!==stations.size||[...assets].some(asset=>!stations.has(asset)))fail('Station selection differs');
  const stationRecords=[...assets].map(asset=>({number:Number(asset.slice(7)),title:read(prefix+'station.'+asset+'.title'),body:read(prefix+'station.'+asset+'.purpose')}));
  // No raw-source URLs, future scene bodies, endings or NPC goals are exposed here.
  return {...fallback,title,intro:situation,startupPreparation:'none',speakerNames,characterProfiles,stationRecords,
    briefing:{title,sections:[{heading:{zh:'時間與地點',en:'When and where'},body:setting},{heading:{zh:'發生緊乜',en:'What is happening'},body:situation},{heading:{zh:'你嘅立場',en:'Your role'},body:role},{heading:{zh:'你要查清楚嘅問題',en:'Your question'},body:question}],closing:{zh:'先認識人物，再查看工作站。原始來源同虛構劇情分開閱讀。',en:'Meet the people, then inspect the stations. Keep original sources distinct from fictional events.'}}};
}
