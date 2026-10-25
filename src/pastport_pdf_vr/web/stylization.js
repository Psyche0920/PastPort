const $ = id => document.getElementById(id);
let selected = null;
let uploading = false;
let previewId = null;
let previewIsEarlier = false;
let refreshInProgress = false;
const expandedEnvironments = new Set();
const statusLabels = {
  prepared: 'Ready to start', running: 'Generating',
  completed: 'Ready to review', recovery_required: 'Needs attention',
};
const formatNumber = value => Number(value).toLocaleString();

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw Error(typeof data.detail === 'string' ? data.detail : 'Please check your input and try again.');
  }
  return data;
}

function estimate(job) {
  selected = job;
  $('estimate').hidden = false;
  const source = job.source;
  $('summary').replaceChildren();
  for (const text of [
    `${job.title} · ${source.viewpoints} viewpoints · ${source.kind === 'scene3d' ? '3D' : 'VR panorama'}`,
    `Initial images: ${source.required_calls}. ${job.execution === 'agent' ? `Agent calls: normally ${job.normal_model_calls}, at most ${job.maximum_model_calls} including one optional repair and reviews.` : 'Fixed generation workflow.'}`,
    `Estimated recorded tokens: ${formatNumber(job.expected_tokens_low)}–${formatNumber(job.expected_tokens_high)} (repair reserve included).`,
    `Suggestions when blank: ${job.maximum_model_calls || source.required_calls} model calls / ${formatNumber(job.suggested_token_threshold)} tokens.`,
  ]) {
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    $('summary').append(paragraph);
  }
  $('calls').value = job.authorized_calls ?? '';
  $('tokens').value = job.authorized_tokens ?? '';
  $('calls').readOnly = job.authorized_calls != null;
  $('tokens').readOnly = job.authorized_tokens != null;
  $('calls').placeholder = `Suggested: ${job.maximum_model_calls || source.required_calls}`;
  $('tokens').placeholder = `Suggested: ${formatNumber(job.suggested_token_threshold)}`;
  $('authorize').checked = false;
  $('generate').textContent = job.status === 'recovery_required' ? 'Resume saved task' : 'Create animated environment';
  $('generate').disabled = job.status === 'running' || job.status === 'completed';
}

function openPreview(job, scroll = true) {
  if (job.status !== 'completed') return;
  const source = `/stylization-results/${job.run_id}/`;
  if (previewId !== job.run_id) {
    previewId = job.run_id;
    $('preview-state').textContent = 'Opening interactive preview…';
    $('preview-frame').src = source;
  }
  $('preview-frame').hidden = false;
  $('preview-empty').hidden = true;
  $('preview-actions').hidden = false;
  previewIsEarlier = Boolean(job.isEarlierVersion);
  $('preview-title').textContent = `${previewIsEarlier ? 'Earlier version · ' : ''}${job.title} · ${job.source.viewpoints} viewpoints`;
  $('open-preview').href = source;
  $('preview-download').href = `/api/stylization/${job.run_id}/download`;
  history.replaceState(null, '', `#preview=${job.run_id}`);
  document.querySelectorAll('.job').forEach(element => {
    element.classList.toggle('current', element.dataset.runId === job.run_id);
  });
  if (scroll) $('preview-panel').scrollIntoView({behavior: 'smooth', block: 'start'});
}

$('preview-frame').addEventListener('load', () => {
  if (previewId) $('preview-state').textContent = previewIsEarlier
    ? 'Showing an earlier completed version. The latest task has no new result yet.'
    : 'Preview window open · visual review pending';
});
$('fullscreen').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $('preview-panel').requestFullscreen();
  } catch {
    $('preview-state').textContent = 'Full screen is unavailable here. Use Open separately.';
  }
};
document.addEventListener('fullscreenchange', () => {
  $('fullscreen').textContent = document.fullscreenElement ? 'Exit full screen' : 'Full screen';
});
$('package').addEventListener('change', () => {
  $('file-selection').textContent = $('package').files[0]?.name ?? 'No file selected · up to 2 GiB';
});
for (const eventName of ['dragenter', 'dragover']) {
  $('upload-drop').addEventListener(eventName, event => {
    event.preventDefault();
    $('upload-drop').classList.add('over');
  });
}
for (const eventName of ['dragleave', 'drop']) {
  $('upload-drop').addEventListener(eventName, event => {
    event.preventDefault();
    $('upload-drop').classList.remove('over');
    if (eventName === 'drop' && !uploading && event.dataTransfer?.files.length) {
      if (event.dataTransfer.files.length !== 1) {
        $('status').textContent = 'Choose one complete tour ZIP at a time.';
        return;
      }
      $('package').files = event.dataTransfer.files;
      $('package').dispatchEvent(new Event('change'));
    }
  });
}
$('upload').onsubmit = async event => {
  event.preventDefault();
  if (uploading) return;
  uploading = true;
  const button = event.target.querySelector('button');
  button.disabled = true;
  $('status').textContent = 'Reading your package. Generation has not started…';
  try {
    const job = await request('/api/stylization/uploads', {
      method: 'POST', headers: {'X-PastPort-Edit': '1'}, body: new FormData(event.target),
    });
    estimate(job);
    $('status').textContent = `New generation task created: ${job.title}. Previous outputs will not be reused. Review the estimate and start when ready.`;
    await refresh();
  } catch (error) {
    $('status').textContent = error.message;
  } finally {
    button.disabled = false;
    uploading = false;
  }
};
$('generate').onclick = async () => {
  if (!selected) return;
  if (!$('authorize').checked) {
    $('status').textContent = 'Review the estimate and check the authorization box to start.';
    $('authorize').focus();
    return;
  }
  if (!$('calls').reportValidity() || !$('tokens').reportValidity()) return;
  $('generate').disabled = true;
  try {
    selected = await request(`/api/stylization/${selected.run_id}/start`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-PastPort-Edit': '1'},
      body: JSON.stringify({
        authorize: true,
        max_calls: $('calls').value ? Number($('calls').value) : null,
        max_recorded_tokens: $('tokens').value ? Number($('tokens').value) : null,
      }),
    });
    $('status').textContent = selected.message;
    await refresh();
  } catch (error) {
    $('status').textContent = error.message;
    $('generate').disabled = false;
  }
};

const progressLabels = {
  ready: 'Ready to start', preparing: 'Preparing source images', planning: 'Agent planning',
  generating: 'Generating initial images', assembling: 'Assembling initial tour',
  reviewing: 'Comparing with your approved reference', repairing: 'Repair round 1 of 1',
  reassembling: 'Assembling repaired tour', final_review: 'Reviewing the repaired images',
  packaging: 'Saving the final package', completed: 'Ready for your review',
  attention: 'Stopped — saved progress needs attention', unavailable: 'Progress temporarily unavailable',
};
let progressApiUnavailable = false;
async function readProgress() {
  try {
    if (!progressApiUnavailable) {
      const response = await fetch('/api/stylization/progress', {cache: 'no-store'});
      if (response.ok) return await response.json();
      if (response.status === 404) progressApiUnavailable = true;
    }
    const bridge = await fetch('/static/.runtime/stylization-progress.json', {cache: 'no-store'});
    return bridge.ok ? await bridge.json() : null;
  } catch { return null; }
}
function progressPanel(job, snapshot) {
  const progress = snapshot?.runs?.find(run => run.run_id === job.run_id);
  const panel = document.createElement('div'); panel.className = 'run-progress';
  const label = document.createElement('p'); label.className = 'progress-heading';
  if (!progress || Date.now() / 1000 - snapshot.generated_at > 15) {
    label.textContent = 'Progress update delayed. The saved task is not restarted.';
    panel.append(label); return panel;
  }
  label.textContent = progressLabels[progress.phase] ?? 'Reading saved progress';
  panel.append(label);
  const indexes = {ready: -1, preparing: 0, planning: 0, generating: 1, assembling: 1,
    reviewing: 2, repairing: 3, reassembling: 3, final_review: 4, packaging: 5, completed: 6};
  const current = indexes[progress.phase] ?? -1;
  const stages = document.createElement('ol'); stages.className = 'progress-stages';
  for (const [index, text] of ['Plan', 'Generate', 'Review', 'Repair if needed', 'Final check', 'Save'].entries()) {
    const step = document.createElement('li');
    const skipped = progress.repair_skipped && (index === 3 || index === 4);
    step.className = skipped ? 'skipped' : index < current ? 'done' : index === current ? 'active' : '';
    step.textContent = skipped ? `${text} · skipped` : text;
    if (index === current) step.setAttribute('aria-current', 'step');
    stages.append(step);
  }
  panel.append(stages);
  const review = progress.phase === 'reviewing' || progress.phase === 'final_review';
  const count = review ? progress.reviews_done : progress.images_done;
  const total = review ? progress.reviews_total : progress.images_total;
  const detail = document.createElement('p'); detail.className = 'progress-detail';
  detail.textContent = review
    ? `${count} / ${total} reference and cross-view checks saved`
    : `${progress.round_number ? 'Repair' : 'Initial'} images: ${count} / ${total} directions saved`;
  if (['generating', 'repairing', 'reviewing', 'final_review', 'assembling', 'reassembling'].includes(progress.phase)) {
    const bar = document.createElement('progress'); bar.max = Math.max(total, 1); bar.value = count;
    bar.setAttribute('aria-label', detail.textContent); panel.append(bar);
  }
  panel.append(detail);
  const faceNames = {front: 'Front', right: 'Right', back: 'Back', left: 'Left', up: 'Ceiling', down: 'Floor'};
  if (progress.views.length && !['ready', 'preparing', 'planning'].includes(progress.phase)) {
    const views = document.createElement('div'); views.className = 'progress-views';
    for (const view of progress.views) {
      const row = document.createElement('div'); row.className = 'progress-view';
      const name = document.createElement('strong'); name.textContent = `Viewpoint ${view.number}`; row.append(name);
      for (const [face, text] of Object.entries(faceNames)) {
        const saved = view.completed_directions.includes(face);
        const item = document.createElement('span'); item.className = `face-status${saved ? ' done' : ''}`;
        item.textContent = `${saved ? '✓' : '○'} ${text}`; item.title = saved ? 'Saved with a completed receipt' : 'Not yet saved';
        row.append(item);
      }
      views.append(row);
    }
    panel.append(views);
  }
  const foot = document.createElement('p'); foot.className = 'progress-foot';
  const minutes = Math.floor(progress.elapsed_seconds / 60), seconds = progress.elapsed_seconds % 60;
  foot.textContent = `${minutes}m ${seconds}s this attempt · ${progress.calls_done} model calls completed${progress.call_in_flight ? ' · one call in progress' : ''} · updates automatically`;
  panel.append(foot); return panel;
}

async function refresh() {
  if (refreshInProgress) return;
  refreshInProgress = true;
  try {
    const rows = await request('/api/stylization/jobs');
    const progress = await readProgress();
    const active = rows.find(row => row.status === 'running');
    $('live-run').hidden = !active;
    $('live-run').replaceChildren();
    if (active) {
      const heading = document.createElement('div'); heading.className = 'panel-heading';
      const title = document.createElement('h2'); title.textContent = `Current task · ${active.title}`;
      heading.append(title); $('live-run').append(heading, progressPanel(active, progress));
    }
    const environments = new Map();
    for (const row of rows) {
      const key = row.source.environment_key || row.upload_sha256;
      if (!environments.has(key)) environments.set(key, []);
      environments.get(key).push(row);
    }
    $('record-count').textContent = `${environments.size} ${environments.size === 1 ? 'environment' : 'environments'} · ${rows.length} versions`;
    const versionTargets = new Map();
    $('jobs').replaceChildren();
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'No saved environments yet. Upload a package to begin.';
      $('jobs').append(empty);
    }
    for (const [key, versions] of environments) {
      const group = document.createElement('section');
      group.className = 'environment-group';
      const heading = document.createElement('div');
      heading.className = 'environment-heading';
      const title = document.createElement('h3');
      title.textContent = versions[0].title.replace(/\.zip$/i, '');
      const count = document.createElement('span');
      count.className = 'badge';
      count.textContent = `${versions[0].source.viewpoints} viewpoints · ${versions.length} versions`;
      heading.append(title, count);
      for (const row of versions) row.isEarlierVersion = row.run_id !== versions[0].run_id;
      const playable = versions.find(row => row.status === 'completed');
      if (playable) {
        const preview = document.createElement('button');
        preview.type = 'button'; preview.className = 'secondary';
        preview.textContent = playable.isEarlierVersion ? 'Preview previous result' : 'Preview latest result';
        preview.onclick = () => openPreview(playable);
        heading.append(preview);
      }
      group.append(heading);
      versionTargets.set(versions[0].run_id, group);
      if (versions.length > 1) {
        const history = document.createElement('details');
        history.className = 'version-history';
        history.open = expandedEnvironments.has(key);
        history.addEventListener('toggle', () => {
          if (history.open) expandedEnvironments.add(key);
          else expandedEnvironments.delete(key);
        });
        const summary = document.createElement('summary');
        summary.textContent = `Earlier versions (${versions.length - 1})`;
        history.append(summary);
        group.append(history);
        for (const row of versions.slice(1)) versionTargets.set(row.run_id, history);
      }
      $('jobs').append(group);
    }
    for (const row of rows) {
      const article = document.createElement('article');
      article.className = `job${previewId === row.run_id ? ' current' : ''}`;
      article.dataset.runId = row.run_id;
      const heading = document.createElement('div');
      heading.className = 'job-top';
      const title = document.createElement('h3');
      title.textContent = row.title;
      const badge = document.createElement('span');
      badge.className = `badge ${row.status}`;
      badge.textContent = statusLabels[row.status] ?? 'Unknown status';
      heading.append(title, badge);
      const meta = document.createElement('p');
      meta.className = 'job-meta';
      meta.textContent = `${row.execution === 'agent' ? 'Agent · approved animation style' : 'Earlier result'} · ${row.source.kind === 'scene3d' ? '3D environment' : 'VR panorama'} · ${row.source.viewpoints} viewpoints`;
      const status = document.createElement('p');
      status.textContent = row.message;

      if (row.upload_names?.length > 1) {
        meta.textContent += ` · Uploaded names: ${row.upload_names.join(' / ')}`;
      }
      const nav = document.createElement('nav');
      if (row.status === 'completed') {
        const preview = document.createElement('button');
        preview.type = 'button';
        preview.textContent = 'Preview';
        preview.onclick = () => openPreview(row);
        const download = document.createElement('a');
        download.textContent = 'Download complete ZIP';
        download.href = `/api/stylization/${row.run_id}/download`;
        nav.append(preview, download);
        if (row.execution === 'agent') {
          const review = document.createElement('a');
          review.textContent = 'Agent review';
          review.href = `/api/stylization/${row.run_id}/review`;
          review.target = '_blank'; review.rel = 'noopener';
          nav.append(review);
        }
      } else if (row.status !== 'running') {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'secondary';
        button.textContent = row.status === 'recovery_required' ? 'Review saved task' : 'Review estimate';
        button.onclick = () => {
          estimate(row);
          $('estimate').scrollIntoView({behavior: 'smooth', block: 'start'});
        };
        nav.append(button);
      }
      article.append(heading, meta, status);
      if (row.execution === 'agent' && row.status !== 'prepared') article.append(progressPanel(row, progress));
      article.append(nav);
      const target = versionTargets.get(row.run_id);
      if (target?.classList.contains('environment-group')) {
        target.insertBefore(article, target.querySelector('.version-history'));
      } else { target?.append(article); }
    }
    if (!previewId) {
      const requested = new URLSearchParams(location.hash.slice(1)).get('preview');
      const initial = rows.find(row => row.status === 'completed' && row.run_id === requested)
        ?? rows.find(row => row.status === 'completed');
      if (initial) openPreview(initial, false);
    }
  } catch (error) {
    $('status').textContent = `Could not load records. ${error.message}`;
  } finally {
    refreshInProgress = false;
  }
}
setInterval(() => { if (!document.hidden) refresh(); }, 4000);
refresh();
