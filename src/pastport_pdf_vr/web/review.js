'use strict';
const projectBase = location.pathname.match(/^\/projects\/[a-f0-9]{32}/)?.[0] || '';
for (const link of document.querySelectorAll('a[data-project-link]')) link.href = projectBase + link.getAttribute('href');
let snapshot, selected;
const el = id => document.getElementById(id);

async function fetchJSON(url, options) {
  const response = await fetch(projectBase+url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '数据校验失败');
  return data;
}

function select(id) {
  selected = snapshot.objects.find(item => item.object.entity.object_id === id);
  if (!selected) return;
  location.hash = encodeURIComponent(id);
  const object = selected.object;
  el('title').textContent = `${object.entity.display_number} · ${object.entity.label}`;
  const origin = selected.origin === 'human' ? '人工版本' : selected.origin === 'ai' ? '默认草稿' : '暂无内容';
  el('assignment').textContent = `历史绑定：${object.historical_subject_id || '暂无历史绑定'} · ${origin}`;
  el('introduction').value = selected.introduction;
  el('background').value = selected.background;
  el('save').disabled = !object.historical_subject_id;
  const gallery=el('photo-observations'); gallery.replaceChildren();
  const photoMode=snapshot.input_binding.startsWith('photo-mapping:');
  el('mapping-downloads').hidden=!photoMode;
  for(const link of document.querySelectorAll('header a[data-project-link]')) link.hidden=photoMode;
  if(object.photo_observations?.length) {
    const heading=document.createElement('h3'); heading.textContent='你的照片：同一对象的全部视角'; gallery.append(heading);
    const views=document.createElement('div'); views.className='photo-views';
    for(const observation of object.photo_observations) {
      const card=document.createElement('figure');
      const image=document.createElement('img'); image.src=projectBase+'/media/'+observation.crop.asset.sha256; image.alt='现场照片中的对象选区';
      const caption=document.createElement('figcaption'); caption.textContent=observation.photo.name+' · '+(observation.identity_state==='confirmed'?'已记录身份':'身份待确认');
      const link=document.createElement('a'); link.href=projectBase+'/media/'+observation.photo.image.asset.sha256; link.target='_blank'; link.rel='noreferrer'; link.textContent='查看完整照片';
      card.append(image,caption,link); views.append(card);
    }
    gallery.append(views);
  }
  el('appearances').replaceChildren();
  for (const row of snapshot.anchors.filter(item => item.anchor.object_id === id)) {
    const link = document.createElement('a');
    link.href = `${projectBase}/vr/?object=${encodeURIComponent(id)}&view=${encodeURIComponent(row.anchor.view_id)}`;
    link.textContent = `在 VR 中查看（${row.origin === 'human' ? '人工位置' : '模型位置'}）`;
    el('appearances').append(link, document.createElement('br'));
  }
  el('evidence').textContent = JSON.stringify({
    mode: snapshot.mode,
    subject: object.historical_subject_id,
    evidence_refs: object.evidence_refs,
    identity_features: object.entity.distinguishing_features,
    assignment_mismatch: selected.assignment_mismatch,
    source: object.replay_evidence,
  }, null, 2);
  const evidence = object.replay_evidence;
  const image = el('source-image');
  image.hidden = !evidence?.source_image;
  if (!image.hidden) image.src = projectBase + '/media/' + evidence.source_image.asset.sha256;
  const page = el('source-page');
  page.hidden = !evidence?.page_image;
  if (!page.hidden) page.href = projectBase + '/media/' + evidence.page_image.asset.sha256;
  el('status').textContent = selected.assignment_mismatch ? '历史绑定已改变，旧人工内容已保留但未套用。' : '';
}

async function load(id) {
  snapshot = await fetchJSON('/api/snapshot');
  const summary = await fetchJSON('/api/build-summary');
  el('build-gaps').hidden = !summary?.gaps.length;
  el('gap-list').replaceChildren();
  for (const gap of summary?.gaps || []) {
    const item = document.createElement('li');
    item.textContent = gap;
    el('gap-list').append(item);
  }
  el('run').textContent = `${snapshot.mode === 'synthetic_replay' ? '离线回放' : '模型结果'} · 数据版本 ${snapshot.revision}`;
  el('objects').replaceChildren();
  const sorted = [...snapshot.objects].sort((a, b) => a.object.entity.display_number - b.object.entity.display_number);
  for (const row of sorted) {
    const button = document.createElement('button');
    button.textContent = `${row.object.entity.display_number} · ${row.object.entity.label}`;
    button.onclick = () => select(row.object.entity.object_id);
    el('objects').append(button);
  }
  select(id || decodeURIComponent(location.hash.slice(1)) || snapshot.objects[0]?.object.entity.object_id);
}

el('save').onclick = async () => {
  if (!selected) return;
  const id = selected.object.entity.object_id;
  const introduction = el('introduction').value;
  const background = el('background').value;
  el('save').disabled = true;
  try {
    await fetchJSON('/api/text', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-PastPort-Edit': '1'},
      body: JSON.stringify({
        operation_id: crypto.randomUUID(), object_id: id,
        historical_subject_id: selected.object.historical_subject_id,
        expected_version: selected.version, introduction, background,
      }),
    });
    await load(id);
    el('status').textContent = '已保存。重新点击 VR 编号可读取最新人工内容。';
  } catch (error) {
    el('status').textContent = error.message + '；草稿仍在输入框，请先复制后重新载入。';
    el('save').disabled = false;
  }
};
load().catch(error => { el('status').textContent = error.message; });
