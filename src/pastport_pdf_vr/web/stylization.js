const $ = id => document.getElementById(id);
let selected = null;
let uploading = false;
let previewId = null;
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
  $('preview-title').textContent = `${job.title} · ${job.source.viewpoints} viewpoints`;
  $('open-preview').href = source;
  $('preview-download').href = `/api/stylization/${job.run_id}/download`;
  history.replaceState(null, '', `#preview=${job.run_id}`);
  document.querySelectorAll('.job').forEach(element => {
    element.classList.toggle('current', element.dataset.runId === job.run_id);
  });
  if (scroll) $('preview-panel').scrollIntoView({behavior: 'smooth', block: 'start'});
}

$('preview-frame').addEventListener('load', () => {
  if (previewId) $('preview-state').textContent = 'Preview window open · visual review pending';
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
    $('status').textContent = job.upload_reused
      ? `Upload recognized: ${job.title}. This matches an existing task; its state and usage are retained. ${job.message}`
      : job.message;
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

async function refresh() {
  if (refreshInProgress) return;
  refreshInProgress = true;
  try {
    const rows = await request('/api/stylization/jobs');
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
      const playable = versions.find(row => row.status === 'completed');
      if (playable) {
        const preview = document.createElement('button');
        preview.type = 'button'; preview.className = 'secondary';
        preview.textContent = 'Preview latest result';
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
      if (row.upload_reused) status.textContent += ' Latest upload matched this existing task.';
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
      article.append(heading, meta, status, nav);
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
