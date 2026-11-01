/** Authored story and presentation data. All personal incidents are fictional. */
export const pair = (zh, en) => ({ zh, en });
const L = pair;
const variable = (name, value) => ({ kind: 'variable_equals', name, value });
const choice = (decision_id, option_id) => ({ kind: 'choice_equals', decision_id, option_id });
export const trust = { kind: 'all', conditions: [variable('owned_error', true), variable('respectful', true)] };
const intro = L('1451年，Bursa。Yusuf十九岁，刚回到母亲身边，在施食所做杂务。他想保住差事，也想学会读写。Murad II归葬的消息传来，这里仍要照常供饭。今天，厨房缺柴，屋面也等着修。', 'Bursa, 1451. Nineteen-year-old Yusuf has returned to his mother and found work at the imaret. He wants a steady living and a chance to learn to read. News of Murad II’s burial has arrived, but meals still have to be served. Today, the kitchen needs fuel and the roof needs work.');
export const chapters = [
  { id: 's01', chapter: 1, title: L('石上写着谁', 'Whose name is on the stone?'),
    body: L('İlyas替Yusuf解释入口的铭文。听到他父亲的名字，忽然问：“Hasan？是不是从前拿过柴的那个人？”\nDavud抬起头：“你见过吗？没见过，就别只剩这一句。”\nYusuf看着他。母亲只说父亲做过木工，这个人却像是知道别的事。', 'İlyas explains the entrance inscription. Hearing Yusuf’s father’s name, he asks, “Hasan? The man who took firewood?”\nDavud looks up. “Did you see it? Then don’t reduce him to that one sentence.”\nYusuf watches him. His mother only told him his father was a carpenter. This man seems to know more.'),
    objects: [68, 64, 67], requiredSources: [68, 64],
    plugin: { kind: 'question', prompt: L('对照入口铭文和饮水泉资料，哪句话站得住？', 'What conclusion do the inscription and fountain records support?'), options: [
      { id: 'date', text: L('入口铭文记营建；泉的铭文虽已失传，仍可从建筑特征讨论年代。', 'The entrance records construction; the fountain can still be studied through its architecture despite its missing inscription.'), correct: true },
      { id: 'none', text: L('泉没有铭文，所以它没有历史来历。', 'The fountain has no historical origin because its inscription is missing.'), feedback: L('字没有留下，不等于设施没有来历。再看64号的建筑描述。', 'A missing inscription does not erase a structure’s history. Read object 64 again.') },
      { id: 'father', text: L('铭文能证明Hasan当年没有拿柴。', 'The inscription proves Hasan never took firewood.'), feedback: L('铭文没有记录Hasan这件私事，不能替他作证。', 'The inscription does not record Hasan’s private story and cannot serve as his witness.') }
    ] },
    after: L('石上记录了营建者，却没有记下每个在这里干活的人。Davud说：“旧事先放一放。你先问清楚，今天到的到底是什么木料。”', 'The stone names the patron, not every worker. Davud says, “Leave the old story for a moment. Find out what kind of timber actually arrived today.”') },
  { id: 's02', chapter: 2, title: L('木头到了，柴却没到', 'Timber arrived. Firewood did not.'),
    body: L('Salih问木料到没到。Yusuf怕显得不懂，答了一句“到了”。\n可修屋顶的长木和做饭的干柴，根本不是一回事。如今锅还等着烧，他却先怀疑：是不是又有人拿走了柴？', 'Salih asked whether the wood had arrived. Afraid of looking foolish, Yusuf said yes.\nBut roof timber and cooking fuel are different supplies. With the pots still waiting, his first thought is: has someone taken the firewood again?'),
    objects: [2, 23], requiredSources: [2, 23],
    plugin: { kind: 'routing', cards: [
      { id: 'a', label: L('长木梁 · 屋面支撑订单', 'Long beam · roof support order'), target: 'roof' },
      { id: 'b', label: L('劈开的干柴 · 厨房燃料订单', 'Split dry firewood · kitchen fuel order'), target: 'fuel' },
      { id: 'c', label: L('木椽 · 修缮订单', 'Rafter · repair order'), target: 'roof' },
      { id: 'd', label: L('短干柴束 · 炊事订单', 'Bundle of short dry wood · cooking order'), target: 'fuel' },
      { id: 'e', label: L('屋面框架用材 · 木工订单', 'Roof framing timber · carpenter’s order'), target: 'roof' },
      { id: 'f', label: L('待补炊柴 · 尚未到货', 'Cooking fuel · delivery still outstanding'), target: 'missing' }
    ], bins: [{id:'roof',label:L('修缮队列','Roof repairs')},{id:'fuel',label:L('厨房队列','Kitchen fuel')},{id:'missing',label:L('缺货复核','Missing delivery')} ] },
    automaticDecision: 'handling', options: [{id:'clean',text:L('已核对','Checked')},{id:'rework',text:L('返工后核对','Checked after rework')}],
    after: L('到货单分开后，缺口就清楚了：修缮木到了，炊柴还缺。Yusuf没找到偷柴的人，先找到了自己报错的那句话。', 'Once the deliveries are separated, the shortage is clear: repair timber arrived; cooking fuel is short. Yusuf has not found a thief. He has found his own mistaken report.') },
  { id: 's03', chapter: 3, title: L('有炉火就能做饭吗', 'Does a hearth make a public kitchen?'),
    body: L('Kemal指着学校：“学生房里也有炉火，先把做饭的活挪过去？”\nYusuf差一点又点头。可房间有炉灶，不等于能给所有人供饭；庭院水池也不等于饮水泉。', 'Kemal points toward the madrasa. “The students’ rooms have hearths. Could we move the cooking there?”\nYusuf almost agrees again. But a room with a hearth is not automatically a public kitchen, and a courtyard pool is not the drinking fountain.'),
    objects: [39, 86, 16, 64], requiredSources: [39, 86, 16],
    plugin: {kind:'question',prompt:L('现在该怎样向Salih纠正？','What can you responsibly report to Salih?'),options:[
      {id:'check',text:L('说清到货与缺货；学生房能否供餐，还缺容量、使用安排等依据。','Separate delivered and missing supplies; cooking in student rooms still needs evidence about capacity and permission.'),correct:true},
      {id:'move',text:L('学生房有炉灶，马上把供餐搬过去。','The rooms have hearths, so move the meal service immediately.'),feedback:L('资料只说明房间有炉灶，没有证明能承担公共供餐。','The source describes hearths, not their capacity or approval for communal cooking.')},
      {id:'water',text:L('庭院里有八角水池，学生房有炉灶，所以它们能直接当饮水点和公共厨房。','The courtyard has an octagonal pool and the student rooms have hearths, so they can serve as a drinking point and public kitchen.'),feedback:L('资料只说明有水池和炉灶，没有说明池水能饮用、学生房能给大家做饭。','The source shows a pool and hearths; it does not say the water is drinkable or the rooms can cook for everyone.')}
    ]},decision:'accountability', options:[
      {id:'own',text:L('“是我没问清。刚才那句‘到了’，我说错了。”','“I did not ask clearly. I was wrong to report it as delivered.”')},
      {id:'blame',text:L('“都是Kemal传错，我只是照他说的回话。”','“Kemal passed on the wrong message. I only repeated it.”')}
    ], after:L('问题总得纠正。但一句话由谁承担，会改变下一次还有谁愿意帮你。','The report must be corrected either way. Who accepts the blame will affect who helps next time.')},
  { id:'s04a',chapter:4,title:L('那夜的柴，送去了哪里','Where did the firewood go?'),
    body:L('Davud还站在入口附近。Yusuf问起父亲，他只说：“他不是你听见的那一个字。”\nYusuf可以追着要一个清白，也可以先问：那夜到底发生了什么？','Davud is still near the entrance. Asked about Hasan, he says, “There was more to him than that one word.”\nYusuf can demand a clean verdict, or ask what happened that night.'),
    objects:[35],requiredSources:[],plugin:{kind:'dialogue',items:[{id:'davud',speaker:'Davud',text:L('“你父亲帮过我。我那时却没替他说话。别急着问他是不是好人，先想想，你愿不愿意把难听的也听完。厨房后来谁补了柴，我不知道；回家问问Meryem吧。”','“Your father helped me. I did not speak up for him. Before you ask whether he was a good man, ask whether you can bear the uncomfortable part too. I do not know who replaced the kitchen fuel. Ask Meryem when you get home.”')}]},decision:'approach',options:[
      {id:'respect',text:L('“我想听完整。也想知道，你当时遇到了什么。”','“I want the whole story. What were you facing that night?”')},
      {id:'accuse',text:L('“他帮过你，你还沉默？你先给我一个交代。”','“He helped you and you kept quiet? You owe me an explanation.”')}
    ],after:L('追问过去，先得决定怎样对待眼前的人。','To ask about the past, Yusuf first has to decide how to treat the person before him.')},
  {id:'s04b',chapter:4,title:L('后来买柴的钱，是谁出的','Who paid for the replacement?'),body:L('Davud不知道后来是谁补上厨房的柴。Yusuf回家问母亲Meryem。','Davud does not know who replaced the kitchen fuel. Yusuf goes home to ask his mother Meryem.'),
    objects:[35,62],requiredSources:[],plugin:{kind:'dialogue',items:[
      {id:'davud',speaker:'Davud',text:L('“我家孩子病着，屋里没柴。Hasan没得到许可，就把厨房的柴送来给我们取暖。他确实拿了。你问我为什么不说？我怕别人问到我头上。”','“My child was ill and our house had no fuel. Hasan brought cooking firewood without permission. He really did take it. Why did I keep quiet? I was afraid of being questioned myself.”'),variants:[{guard:variable('respectful',false),text:L('“他帮过我，这件事我不会否认。但你现在要我当众认罪，我说不下去。你只听到我承认受过帮助，别替我补出别的话。”','“He helped me; I will not deny it. But I cannot speak while you demand a public confession. You have heard only that I received help. Do not invent the rest.”')}]},
      {id:'mother',speaker:'Meryem',text:L('“后来是我拿家里的应急钱买柴补上的。Hasan告诉我，他把柴送去Davud家取暖。我没亲眼看见他拿柴。”','“I used our emergency savings to replace the firewood. Hasan told me he had taken it to keep Davud’s family warm. I did not see him take it.”')}
    ]},decision:'privacy',options:[
      {id:'ask',text:L('先征求他们的同意，只转述自己确实听到的部分。','Ask their permission and repeat only what you actually heard.')},
      {id:'share',text:L('先把听到的事当众说出去，再向他们解释。','Tell others what you heard first, and explain to them afterwards.')}
    ],after:L('父亲确实帮了人，也确实拿了公物。母亲的钱补上了缺口。给父亲一句好话，不能让这些代价消失。','Hasan helped someone and took public supplies. Meryem’s money filled the gap. A kind word about him cannot erase those costs.')},
  {id:'s05',chapter:5,title:L('先把屋面护住','Protect the roof first'),body:L('旧事听完，今天的活还在。Davud把有限的板料摆出来：“你帮我看看，怎么把要护的地方盖住。”\n母亲也还在等一句话：家里的备用钱，Yusuf会不会又不声不响替大家作主？','The past has been heard, but today’s work remains. Davud lays out the limited panels. “Help me work out how to cover the area.”\nMeryem is waiting too: will Yusuf decide how to spend the household reserve without telling her?'),
    objects:[2,40,62],requiredSources:[2],plugin:{kind:'tiling',width:4,height:4,pieces:[[2,2],[3,1],[3,1],[2,1],[2,1],[2,1]]},decision:'mother-consent',options:[
      {id:'consult',text:L('先陪母亲走一段，把今天缺钱的事和她说清楚。','Spend time with Meryem and explain the shortage before making a decision.')},
      {id:'skip',text:L('先安排工作，家里的钱等用了再解释。','Arrange the work first; explain the household money afterwards if you use it.')}
    ],after:L('拼好的是一份安排，还不是修好的屋面。柴、工钱和人手的缺口，仍得有人承担。','The completed puzzle is a plan, not a repaired roof. Fuel, money and labour still have to be provided.')},
  {id:'s06',chapter:6,title:L('这一回，代价由谁出','Who pays this time?'),body:L('今天公用的钱有4份。补齐炊柴要2份，临时修缮要3份，其中1份是帮工的钱。总共还差1份。\nSalih说：“别再回一句‘到了’。你选怎么补，就得把后面的事做完。”','There are four units of public funds. Cooking fuel costs two; the temporary repair costs three, including one unit for a helper. One unit is missing.\nSalih says, “Do not just tell me it is done. Choose how to fill the gap, then fulfil your promise.”'),
    objects:[23,2,67],requiredSources:[],plugin:{kind:'budget',public:4,fuel:2,repair:3,plans:[
      {id:'family',label:L('用家庭备用钱补1份','Add one unit from the household reserve'),detail:L('按原安排完成工作，赶上读写约定；家里的余钱会减少。','Keep the work and literacy appointment on schedule, at the cost of the household reserve.'),funds:5,cost:5},
      {id:'davud',label:L('接受Davud的互助约定','Accept Davud’s offer'),detail:L('Davud补1份，你答应随他外出学手艺；眼前的差事和读写约定要放下。','Davud adds one unit; you join his travelling repair crew and give up this job and today’s literacy appointment.'),funds:5,cost:5,guard:trust,locked:L('Davud还不愿作这个承诺：需要先承担自己的错误，并认真听他把话说完。','Davud will not make this commitment without accountability and a respectful conversation.')},
      {id:'labor',label:L('自己做帮工，少支出1份','Do the helper’s work yourself'),detail:L('保住家用钱和差事，错过这次读写约定。','Keep the household reserve and your job, but miss the literacy appointment.'),funds:4,cost:4}
    ]},automaticDecision:'funding',options:[{id:'family',text:L('家庭备用钱','Household reserve')},{id:'davud',text:L('工匠互助','Davud’s offer')},{id:'labor',text:L('自行帮工','Your own labour')}],after:L('决定已经记下。现在，把承诺做完。','Your commitment is recorded. Now fulfil it.')},
  {id:'s07',chapter:6,title:L('把今天做完','Finish today’s work'),body:L('选择落到了自己身上。这一次，不能让别人替自己把话圆回去。','The choice is yours now. This time, someone else cannot quietly cover its cost.'),objects:[67,68],requiredSources:[],
    plugin:{kind:'dialogue',commitments:true,items:[
      {id:'fuel',speaker:'Salih',text:L('确认补来的炊柴交到厨房，供餐可以继续。','Confirm the replacement fuel reaches the kitchen so the meal service can continue.')},
      {id:'promise',speaker:'Yusuf',text:L('把家用钱的去向告诉Meryem，再按原安排交接修缮。','Tell Meryem how the reserve was used, then hand over the repair work as arranged.'),variants:[
        {guard:variable('funding','davud'),text:L('和Davud说清同行约定，向Salih交接差事，也告诉母亲自己何时离开。','Agree the terms with Davud, hand over your job to Salih and tell Meryem when you will leave.')},
        {guard:variable('funding','labor'),text:L('留下搬运、清场，完成帮工的份额；给İlyas带话，承认自己赶不上这次约定。','Stay to carry materials and clear the work area. Send word to İlyas that you will miss the appointment.')}
      ]}
    ]}}
];
export const endings = [
  {id:'E01',route:'family',title:L('带着代价留下','Stay, at a cost'),text:L('Yusuf赶上了读写约定，差事也保住了。家里的备用钱却少了一份。若他提前问过，母亲至少知道自己也在这次决定里；若他先花后说，这个儿子便又走了一次父亲走过的路。','Yusuf keeps his job and his literacy appointment, but the household reserve is smaller. If he asked first, Meryem shared in the decision. If not, he has repeated a part of his father’s mistake.')},
  {id:'E02',route:'davud',title:L('带着承诺离开','Leave with a promise'),text:L('Davud补了钱，Yusuf跟他外出学手艺。他没有替父亲换来一个干净结论，却给自己换了一条路。母亲送他时并不轻松；能学手艺，也意味着要离开她。','Davud fills the gap and Yusuf leaves to learn a trade. He has not obtained a spotless verdict for his father, but he has found another path. Learning a craft also means leaving his mother.')},
  {id:'E03',route:'labor',title:L('把今天做完','Finish today’s work'),text:L('Yusuf把今天的活做完了，家用钱还在，差事也还在。等他擦净手，İlyas早已走了。以后或许还能学，但这一次已经错过。他心里踏实，也有不甘。','Yusuf finishes the work, keeping the household reserve and his job. By the time he washes his hands, İlyas has gone. There may be another chance to learn, but this one is lost. He feels both steady and dissatisfied.')}
];
export const sourceNotes = {
  2:L('施食所的木构四坡瓦屋顶；木材信息来自文字，临时修缮为原创。','The imaret has a hipped timber roof with tiles. Timber construction comes from the text; today’s repair is fictional.'),
  16:L('学校庭院八角形大理石水池，与饮水泉是不同设施。','The madrasa courtyard’s octagonal marble pool is distinct from the drinking fountain.'),
  22:L('东侧宣礼塔较早，不足以证明现状的每处细节都属于1451年。','The eastern minaret is earlier, but not every present detail is established as dating to 1451.'),
  23:L('施食所的炉灶遗迹；木柴库来自同页更广的建筑背景。','Remains of ovens in the imaret; the wood store is described in the broader page context.'),
  26:L('学校庭院玻璃顶盖来自近代修缮，不能放进1451年的现场。','The glass courtyard cover is a recent restoration feature, not part of the 1451 setting.'),
  35:L('清真寺入口阶梯。这里只作为约见与导航入口。','The mosque entrance steps serve as a meeting and navigation anchor.'),
  36:L('陵墓北侧罩棚装饰画布，年代未明；不是墓棺罩布。','Decorative canvas on the tomb’s northern canopy, of uncertain date; not a sarcophagus covering.'),
  39:L('学校教学空间的砖地面，不能据此证明公共厨房容量。','Brick flooring in the teaching iwan does not establish capacity for public cooking.'),
  40:L('Murad II归葬与简朴遗愿的背景；现状绿色围栏年代未明。','Background on Murad II’s burial and wish for simplicity; the date of the present green railing is uncertain.'),
  62:L('Hüma Hatun陵入口，1449年的营建背景；现代玻璃门不是旧门材质。','Entrance to Hüma Hatun’s tomb, with a 1449 construction background. The modern glass proxy is not the historic door material.'),
  64:L('Sıbyan Mektebi饮水泉。铭文已失传，原书依据建筑特征讨论年代。','The Sıbyan Mektebi fountain. Its inscription is lost; the book discusses its date using architectural characteristics.'),
  67:L('清真寺主入口现状木门，不能断言是1451年原门扇。','The present wooden main entrance door is not established as the original 1451 leaf.'),
  68:L('入口上方营建铭文，记1425—1426年营建，不记Hasan这件私事。','The entrance inscription records construction in 1425–1426, not Hasan’s private story.'),
  86:L('学生房间各有窗、壁龛和炉灶；不指定无依据的住户。','Student rooms each have a window, niche and hearth; no unsupported individual occupant is assigned.')
};
export function createGame(evidenceHash, narrativeHash, objects) {
  const locales={zh:new Map(),en:new Map()};
  const text=(key,value)=>{for(const locale of ['zh','en'])locales[locale].set(key,value[locale]);return key;};
  text('hero-name',L('Yusuf','Yusuf'));text('hero-goal',L('保住生计，也学会为自己的决定负责。','Keep a livelihood and take responsibility for personal choices.'));
  text('accessible',L('所有操作均有按钮与键盘方式。','All actions have button and keyboard controls.'));
  const rules=[],decisions=[];
  const addRule=(id,event,target,guard,effects)=>rules.push({rule_id:id,priority:0,event,target_id:target,guard,effects,once_key:`once:${id}`});
  const always=variable('started',true);
  const set=(name,value)=>({kind:'set_variable',name,value});
  const scenes=chapters.map((c,index)=>{
    text(`${c.id}-title`,c.title);text(`${c.id}-body`,c.body);text(`${c.id}-goal`,c.plugin.prompt??c.title);text(`${c.id}-done`,c.after??L('今天的承诺已经做完。','Today’s commitment is fulfilled.'));text(`${c.id}-hint`,L('查看本章资料与任务提示。','Review this chapter’s sources and task hints.'));
    const task=`task-${c.id}`;
    const next=chapters[index+1]?.id;
    const decision=c.decision??c.automaticDecision??null;
    if(decision){
      decisions.push({decision_id:decision,options:c.options.map(o=>({option_id:o.id,text_key:text(`${decision}-${o.id}`,o.text)}))});
      const effects={accountability:{own:[set('owned_error',true)],blame:[set('owned_error',false)]},approach:{respect:[set('respectful',true)],accuse:[set('respectful',false)]},privacy:{ask:[set('privacy_consent',true)],share:[set('privacy_consent',false)]},'mother-consent':{consult:[set('mother_consulted',true)],skip:[set('mother_consulted',false)]},funding:{family:[set('funding','family'),set('public_remaining',0),set('private_contribution',1),set('fuel_payment',2),set('repair_payment',3),set('literacy_missed',false)],davud:[set('funding','davud'),set('public_remaining',0),set('davud_contribution',1),set('fuel_payment',2),set('repair_payment',3),set('departing',true),set('literacy_missed',true)],labor:[set('funding','labor'),set('public_remaining',0),set('fuel_payment',2),set('repair_payment',2),set('labor_owed',true),set('literacy_missed',true)]},handling:{clean:[set('handling_rework',false)],rework:[set('handling_rework',true)]}};
      for(const opt of c.options){const es=[...(effects[decision]?.[opt.id]??[])];if(next)es.push({kind:'unlock_scene',scene_id:next});let g=choice(decision,opt.id);if(decision==='funding'&&opt.id==='davud')g={kind:'all',conditions:[g,trust]};addRule(`choose-${decision}-${opt.id}`,'option_chosen',decision,g,es);}
    } else if(next)addRule(`done-${c.id}`,'task_completed',task,always,[{kind:'unlock_scene',scene_id:next}]);
    if(c.id==='s04b'){
      addRule('heard-mother','task_completed',task,always,[set('heard_mother',true)]);
      addRule('heard-davud','task_completed',task,variable('respectful',true),[set('heard_davud',true)]);
    }
    if(!next){addRule('finish-services','task_completed',task,always,[set('labor_owed',false),set('services_completed',true)]);addRule('finish-chapter','task_completed',task,always,[{kind:'resolve_ending',ending_table_id:'personal-fates'}]);}
    const refs=(c.objects.length?c.objects:[68]).map(n=>`object-${n}`);
    return {scene_id:c.id,site_id:'murat-complex',title_key:`${c.id}-title`,body_key:`${c.id}-body`,tasks:[{task_id:task,kind:'inspect',objective_key:`${c.id}-goal`,prerequisite_task_ids:[],guard:null,evidence_refs:refs,character_goal_link:'yusuf',feedback_key:`${c.id}-done`,hint_keys:[`${c.id}-hint`],accessibility_key:'accessible',asset_id:`source-${(c.objects[0]??68)}`,spots:[{spot_id:'result',x:5000,y:5000,text_key:`${c.id}-goal`,claim_ids:refs}],required_spot_ids:['result']}],required_task_ids:[task],decision_id:decision,next_scene_ids:next?[next]:[],feedback:[]};
  });
  const endingTable={ending_table_id:'personal-fates',endings:endings.map((e,index)=>({ending_id:e.id,priority:index,guard:variable('funding',e.route),fallback:e.id==='E03',outcomes:[{outcome_id:`fate-${e.id}`,label_key:text(`ending-${e.id}-title`,e.title),text_key:text(`ending-${e.id}-body`,e.text),variants:[]}]}))};
  const game={chapter_id:'one-bundle-of-firewood',protagonist:'yusuf',characters:[{character_id:'yusuf',name_key:'hero-name',goal_key:'hero-goal'}],scenes,props:[],decisions,variables:[{name:'started',initial:true},{name:'owned_error',initial:false},{name:'respectful',initial:false},{name:'privacy_consent',initial:false},{name:'mother_consulted',initial:false},{name:'heard_mother',initial:false},{name:'heard_davud',initial:false},{name:'handling_rework',initial:false},{name:'funding',initial:'none'},{name:'public_remaining',initial:4},{name:'private_contribution',initial:0},{name:'davud_contribution',initial:0},{name:'fuel_payment',initial:0},{name:'repair_payment',initial:0},{name:'labor_owed',initial:false},{name:'services_completed',initial:false},{name:'departing',initial:false},{name:'literacy_missed',initial:false}],rules,endings:[endingTable],initial_state:{current_scene_id:'s01',inventory:[],unlocked_scene_ids:['s01'],elapsed_minutes:0},locales:['en','zh'].map(locale=>({locale,entries:[...locales[locale]].map(([key,text])=>({key,text})).sort((a,b)=>a.key.localeCompare(b.key))}))};
  return {project_id:'murat-story-demo',schema_version:'0.1.0',content_version:'demo-1',package_id:'murat-one-bundle',runtime_compatibility:{profile:'t1a-single-task',contract_version:'0.1.0',task_kinds:['inspect','caseboard'],condition_kinds:['all','any','not','observed_all','choice_equals','variable_equals','has_evidence','elapsed_gt'],effect_kinds:['grant_item','set_variable','set_relationship','add_story_time','unlock_scene','resolve_ending'],event_kinds:['spot_observed','board_submitted','option_chosen','task_completed'],locales:['en','zh'],max_events_per_action:2,max_effects_per_action:64,max_condition_depth:8},evidence_package_hash:evidenceHash,narrative_package_hash:narrativeHash,game,media_manifest:objects.map(o=>({asset_id:`source-${o.number}`,sha256:o.media_sha256,relative_path:o.media_path}))};
}
export const presentation = {intro,chapters,endings,sourceNotes};
