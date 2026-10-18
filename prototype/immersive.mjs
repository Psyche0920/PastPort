/** Contemporary panorama presentation, independent of the historical game state. */
const ENTRIES = Object.freeze([
  { id: 'madrasa', url: 'https://www.bursa.bel.tr/panorama/sanalmuze/kuran-panorama/index.html', title: 'Muradiye 学院与庭院', short: '学院与庭院', description: '沿画面中的白色箭头穿过门厅，进入庭院。拖动环视，抬头看拱券与玻璃顶，再沿原生热点进入展室。' },
  { id: 'complex', url: 'https://www.bursa.bel.tr/panorama/sanaltarihimekan/muradiye/index.html', title: 'Muradiye 建筑群', short: '建筑群与陵墓', description: '从树影与石阶间走入建筑群。点击原生白色箭头可前往清真寺和陵墓室内，拖动查看穹顶、彩釉与窗间的光。' },
]);
const $ = selector => document.querySelector(selector);
const frame = $('#panorama');
const nav = $('#scene-nav');
const dialog = $('#sources-dialog');
let mode = 'tour';
let entryIndex = 0;
let photoIndex = 1;
let chapter;
let catalogue;
let photoScale = 1;
let offset = { x: 0, y: 0 };
let drag = null;
let statusTimer;

function report(message) {
  $('#status').textContent = message;
  $('#status').hidden = false;
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { $('#status').hidden = true; }, 4500);
}

function selectEntry(index) {
  entryIndex = index;
  const entry = ENTRIES[index];
  const url = entry.url;
  frame.src = url;
  $('#external-tour').href = url;
  $('#entry-title').textContent = entry.title;
  $('#entry-description').textContent = entry.description;
  renderNavigation();
}

function renderNavigation() {
  nav.replaceChildren();
  const records = mode === 'tour' ? ENTRIES : chapter?.photos || [];
  records.forEach((record, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-pressed', String(index === (mode === 'tour' ? entryIndex : photoIndex)));
    const number = document.createElement('small');
    number.textContent = String(index + 1).padStart(2, '0');
    button.append(number, document.createTextNode(mode === 'tour' ? record.short : ['建筑群鸟瞰', '学院庭院', '饮水喷泉', '食堂外观', '食堂内部'][index]));
    button.addEventListener('click', () => mode === 'tour' ? selectEntry(index) : selectPhoto(index));
    nav.append(button);
  });
}

function setMode(next) {
  if (next === 'photo' && !chapter) return report('照片档案尚未载入，请稍后重试。');
  mode = next;
  $('#tour-view').hidden = mode !== 'tour';
  $('#photo-view').hidden = mode !== 'photo';
  $('#tour-mode').setAttribute('aria-pressed', String(mode === 'tour'));
  $('#photo-mode').setAttribute('aria-pressed', String(mode === 'photo'));
  $('#collection-label').textContent = mode === 'tour' ? 'THE LIVING ARCHIVE' : 'FROM THE PUBLICATION';
  $('#collection-subtitle').textContent = mode === 'tour' ? '选择一个入口，自由探索' : '拖动、放大，发现原图细节';
  // Unmount the external document to stop its audio, rendering and requests.
  if (mode === 'photo') { frame.removeAttribute('src'); selectPhoto(photoIndex); }
  else selectEntry(entryIndex);
  renderNavigation();
}

function selectPhoto(index) {
  photoIndex = index;
  const photo = chapter.photos[index];
  const scene = chapter.scenes.find(item => item.photo_id === photo.id);
  const image = $('#archive-photo');
  image.src = photo.file;
  image.alt = photo.caption;
  $('#photo-title').textContent = ['建筑群鸟瞰', '学院庭院', '饮水喷泉', '食堂外观', '食堂内部'][index];
  $('#photo-caption').textContent = `${photo.caption} · 出版物第 ${photo.printed_page} 页 · 当代照片`;
  $('#photo-provenance').textContent = `当前照片：${photo.file}；来源 ${photo.source_id}；PDF 第 ${photo.pdf_page} 页，印刷页 ${photo.printed_page}。`;
  $('#observation-title').textContent = '在画面中寻找细节';
  $('#observation-text').textContent = scene?.task.hotspots?.length ? '点击金色标记，阅读现有章节里的建筑观察。可拖动照片或使用下方按钮缩放。' : '这张照片保留出版物原有画幅，可拖动和放大查看。';
  $('#photo-hotspots').replaceChildren();
  for (const spot of scene?.task.hotspots || []) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'hotspot';
    button.style.left = `${spot.x}%`; button.style.top = `${spot.y}%`;
    button.textContent = '＋'; button.setAttribute('aria-label', spot.label);
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => {
      $('#photo-hotspots').querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      $('#observation-title').textContent = spot.label;
      const claim = catalogue.claims.find(item => item.id === spot.claim_id);
      $('#observation-text').textContent = spot.text + (claim ? ` 原书出处：印刷页 ${photo.printed_page}。` : '');
    });
    $('#photo-hotspots').append(button);
  }
  resetPhoto();
  renderNavigation();
}

function placePhoto() {
  const image = $('#archive-photo');
  if (!image.naturalWidth || !image.naturalHeight) return;
  const viewport = $('#photo-viewport');
  const width = viewport.clientWidth;
  const height = viewport.clientHeight;
  if (!width || !height) return;
  // Use the intact photograph as one coordinate plane, including its hotspots.
  const baseScale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
  const planeWidth = image.naturalWidth * baseScale;
  const planeHeight = image.naturalHeight * baseScale;
  const limitX = Math.max(0, (planeWidth * photoScale - width) / 2);
  const limitY = Math.max(0, (planeHeight * photoScale - height) / 2);
  offset.x = Math.max(-limitX, Math.min(limitX, offset.x));
  offset.y = Math.max(-limitY, Math.min(limitY, offset.y));
  const plane = $('#photo-plane');
  plane.style.width = `${planeWidth}px`; plane.style.height = `${planeHeight}px`;
  plane.style.transform = `translate(-50%, -50%) translate(${offset.x}px, ${offset.y}px) scale(${photoScale})`;
}
function resetPhoto() { photoScale = 1; offset = { x: 0, y: 0 }; placePhoto(); }
function zoom(delta) { photoScale = Math.max(1, Math.min(3, photoScale + delta)); placePhoto(); }

$('#archive-photo').addEventListener('load', resetPhoto);
$('#archive-photo').addEventListener('error', () => report('此照片无法载入，请选择另一张。'));
$('#tour-mode').addEventListener('click', () => setMode('tour'));
$('#photo-mode').addEventListener('click', () => setMode('photo'));
$('#sources-button').addEventListener('click', () => dialog.showModal());
$('#close-sources').addEventListener('click', () => dialog.close());
$('#focus-button').addEventListener('click', event => {
  const focused = document.body.classList.toggle('focus-mode');
  event.currentTarget.setAttribute('aria-pressed', String(focused));
  event.currentTarget.textContent = focused ? '显示界面' : '专注观看';
  placePhoto();
});
$('#fullscreen-button').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
    else report('此浏览器不支持全屏，请使用专注观看。');
  } catch (error) { console.warn('Fullscreen unavailable', error.name); report('未能进入全屏，请使用专注观看。'); }
});
$('#zoom-in').addEventListener('click', () => zoom(.2));
$('#zoom-out').addEventListener('click', () => zoom(-.2));
$('#reset-photo').addEventListener('click', resetPhoto);
const viewport = $('#photo-viewport');
viewport.addEventListener('pointerdown', event => {
  if (event.target.closest('button') || !event.isPrimary) return;
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, originX: offset.x, originY: offset.y };
  viewport.setPointerCapture(event.pointerId); viewport.classList.add('dragging');
});
viewport.addEventListener('pointermove', event => {
  if (!drag || event.pointerId !== drag.id) return;
  offset = { x: drag.originX + event.clientX - drag.x, y: drag.originY + event.clientY - drag.y }; placePhoto();
});
function endDrag() { drag = null; viewport.classList.remove('dragging'); }
viewport.addEventListener('pointerup', endDrag);
viewport.addEventListener('pointercancel', endDrag);
viewport.addEventListener('lostpointercapture', endDrag);
viewport.addEventListener('wheel', event => { event.preventDefault(); zoom(event.deltaY < 0 ? .1 : -.1); }, { passive: false });
viewport.addEventListener('keydown', event => {
  const shifts = { ArrowLeft: [45, 0], ArrowRight: [-45, 0], ArrowUp: [0, 45], ArrowDown: [0, -45] };
  if (shifts[event.key]) { event.preventDefault(); offset.x += shifts[event.key][0]; offset.y += shifts[event.key][1]; placePhoto(); }
  else if (event.key === '+' || event.key === '=') zoom(.2);
  else if (event.key === '-') zoom(-.2);
  else if (event.key === '0') resetPhoto();
});
window.addEventListener('resize', placePhoto);
frame.addEventListener('error', () => report('外部全景暂不可用，可打开原站或切换照片探索。'));
selectEntry(0);
async function loadArchive() {
  try {
    const responses = await Promise.all(['../data/locales/zh/muradiye-story.json', '../data/locales/zh/muradiye.json'].map(url => fetch(url)));
    if (responses.some(response => !response.ok)) throw new Error('Archive HTTP failure');
    [chapter, catalogue] = await Promise.all(responses.map(response => response.json()));
    if (!Array.isArray(chapter.photos) || !Array.isArray(chapter.scenes) || !Array.isArray(catalogue.claims)) throw new Error('Invalid archive contract');
    const photo = chapter.photos[photoIndex];
    $('#photo-provenance').textContent = `照片来源 ${photo.source_id}；PDF 第 ${photo.pdf_page} 页，印刷页 ${photo.printed_page}。`;
  } catch (error) { console.error('Could not load local archive', error); report('照片档案读取失败，360° 实景仍可使用。'); }
}
void loadArchive();
