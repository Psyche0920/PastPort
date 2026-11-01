/** Per-object staging data; floor masks are game presentation, not surveyed geometry. */
export function createShots(tour) {
  const first=tour.scenes[0];
  const bindings={2:['s02','s05'],16:['s03'],22:[],23:['s02','s06'],62:['s04b'],64:['s01','s03'],67:['s01','s04a','s07'],68:['s01','s07'],86:['s03']};
  const viewOnly={26:'玻璃顶盖属于后世修缮，本段故事只提供史料查看。',35:'目标位于中庭另一侧，当前没有确认可用的接近地面。',36:'目标位于中庭另一侧，且画布年代未明，保留资料查看。',39:'该目标对应下层地面，不让角色越过当前视点的栏杆。',40:'该目标对应中庭栏板，当前未确认可通行的接近位置。'};
  return first.hotspots.filter(h=>h.type==='info').map(h=>{
    const number=Number(h.label),roof=number===2;
    const shot={number,taskScenes:bindings[number]??[],sceneId:first.id,available:!(number in viewOnly),reason:viewOnly[number]??'',camera:{yaw:h.yaw,pitch:roof?11:Math.max(-19,Math.min(-10,h.pitch-13)),hfov:roof?120:97},boundary:roof?[[9,82],[48,73],[70,84],[76,97],[9,97]]:[[10,75],[46,62],[60,76],[65,97],[10,97]],obstacles:[],spawn:roof?[25,95]:[25,95],approach:roof?[46,86]:[40,83],actors:roof?[[57,85],[65,90]]:[[51,76],[58,84]],radius:32,annotation:roof?'在可见地面仰看屋面，不登高或攀爬。':'仅在当前画面已标定的局部地面接近。'};
    return shot;
  });
}
export const stageTargets={s01:68,s02:23,s03:16,s04a:67,s04b:62,s05:2,s06:23,s07:67};
export const castByStage={s01:['İlyas','Davud'],s02:['Salih','Kemal'],s03:['Kemal','Salih'],s04a:['Davud'],s04b:['Meryem','Davud'],s05:['Davud','Meryem'],s06:['Salih','Davud'],s07:['Salih','Davud']};
export const castFrames={'İlyas':0,Meryem:1,Davud:2,Kemal:3,Salih:3,Yusuf:1};

export const castRows={Yusuf:0};
