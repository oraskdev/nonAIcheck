(() => {
  'use strict';
  const results = document.querySelector('#research-results');
  const status = document.querySelector('#copy-status');
  const escape = (value = '') => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isScore = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
  const score = value => isScore(value) ? (value * 100).toFixed(2) : 'Unavailable';
  const notes = value => Array.isArray(value) ? value.map(v => typeof v === 'string' ? v : v?.message || v?.reason || JSON.stringify(v)) : value ? [String(value)] : [];
  const prose = value => String(value ?? '').split(/\n\s*\n/).filter(Boolean).map(p => `<p dir="auto">${escape(p)}</p>`).join('');
  const hash = value => value ? `<div class="hash">Text SHA-256<code>${escape(value)}</code></div>` : '';
  const trialId = value => 'trial-' + encodeURIComponent(String(value));
  let data, statusTimer;

  function notify(message) {
    clearTimeout(statusTimer);
    status.textContent = message;
    statusTimer = setTimeout(() => { status.textContent = ''; }, 4500);
  }

  function pair(label, value) {
    return `<div class="score-pair"><span>${label}</span><strong${isScore(value) ? '' : ' class="unavailable"'}>${score(value)}</strong></div>`;
  }

  function scoreCard(title, description, entry) {
    return `<section class="score-card"><h2>${escape(title)}</h2><p>${escape(description)}</p>${pair('Desklib / 100', entry?.desklib)}${pair('Vanguard / 100', entry?.vanguard)}</section>`;
  }

  function documentCard(title, description, entry, key) {
    return `<section class="panel"><div class="panel-head"><h2>${escape(title)}</h2><p>${escape(description)}</p><div class="actions"><button class="button" data-action="copy" data-entry="${key}">Copy text</button><button class="button" data-action="download" data-entry="${key}">Download TXT</button></div></div><div class="document-text">${prose(entry.text)}</div>${hash(entry.sha256)}</section>`;
  }

  function render(record) {
    data = record;
    if (!Array.isArray(data.trials) || !data.original || !data.baseline) throw new Error('Incomplete research record');
    const repairs = Array.isArray(data.repairs) ? data.repairs : [];
    const selected = data.selected;
    const selectedId = selected ? String(selected.id) : null;
    const cost = typeof data.estimated_api_cost_usd === 'number' && Number.isFinite(data.estimated_api_cost_usd)
      ? `<span>Estimated API usage: $${data.estimated_api_cost_usd.toFixed(2)} · hosting excluded</span>` : '';
    const selectedRepair = selected && repairs.some(r => String(r.id) === String(selected.id));
    const selectedDescription = selected ? (selectedRepair ? selected.name + ' · additional source-fidelity correction' : `Trial ${selected.id} · ${selected.name}`) : '';
    const renderRows = entries => entries.map(trial => {
      const chosen = selectedId !== null && String(trial.id) === selectedId;
      const eligible = trial.eligible === true;
      const assessmentStatus = isScore(trial.desklib) && isScore(trial.vanguard) ? 'Rejected' : 'Failed / unavailable';
      return `<tr${chosen ? ' class="selected-row"' : ''}><td>${escape(trial.id)}</td><td class="trial-name">${escape(trial.name)}${chosen ? '<br><span class="badge selected">Research selection</span>' : ''}<a href="#${trialId(trial.id)}" data-open-trial="${escape(trial.id)}">Read draft and review notes</a></td><td>${escape(trial.writer)}</td><td>${repairs.includes(trial) ? 'Recorded trial draft' : trial.from_baseline ? 'Previous live output' : 'Original source'}</td><td class="numeric">${score(trial.desklib)}</td><td class="numeric">${score(trial.vanguard)}</td><td><span class="badge${eligible ? '' : ' rejected'}">${eligible ? 'Eligible for comparison' : assessmentStatus}</span></td></tr>`;
    }).join('');
    const rows = renderRows(data.trials);
    const repairPanel = repairs.length ? `<section class="panel"><div class="panel-head"><h2>Additional source-fidelity corrections</h2><p>These are subsequent corrections to recorded trials, not extra original strategies. The ten trial measurements above remain unchanged. Each corrected text was assessed again.</p></div><div class="table-scroll" role="region" aria-label="Fidelity correction measurements; scroll horizontally on small screens" tabindex="0"><table><caption>Separately recorded corrections, on the same 0–100 scales.</caption><thead><tr><th scope="col">Record</th><th scope="col">Correction</th><th scope="col">Writer</th><th scope="col">Starting point</th><th scope="col">Desklib</th><th scope="col">Vanguard</th><th scope="col">Source review</th></tr></thead><tbody>${renderRows(repairs)}</tbody></table></div></section>` : '';
    const trialTexts = [...data.trials, ...repairs].map(trial => {
      const isRepair = repairs.includes(trial);
      const audit = notes(trial.audit_notes);
      const seconds = typeof trial.seconds === 'number' && Number.isFinite(trial.seconds) ? ` · ${trial.seconds.toFixed(1)} seconds` : '';
      return `<details class="trial-details" id="${trialId(trial.id)}"><summary>${isRepair ? 'Additional correction' : 'Trial ' + escape(trial.id)} · ${escape(trial.name)}<span>${escape(trial.writer)}${seconds}</span></summary><div class="audit"><strong>Source-review notes</strong>${audit.length ? `<ul>${audit.map(note => `<li>${escape(note)}</li>`).join('')}</ul>` : '<p>No additional review notes recorded.</p>'}<p>${trial.eligible === true ? 'Eligible for this comparison; this is not an authorship or factual-accuracy certification.' : 'Not eligible for selection. Any recorded draft is shown for inspection only.'}</p></div><div class="document-text">${trial.text ? prose(trial.text) : '<p>No completed draft was recorded.</p>'}</div>${hash(trial.sha256)}</details>`;
    }).join('');
    results.innerHTML = `<div class="record-meta"><span>Recorded: ${escape(data.tested_at)} · ${data.trials.length} trials reported${repairs.length ? ' · ' + repairs.length + ' additional source-fidelity correction(s)' : ''}</span>${cost}</div><p class="summary">${escape(data.summary)}</p>${data.trials.length !== 10 ? '<div class="notice"><strong>This record is incomplete.</strong> Not all ten trial results are available.</div>' : ''}<div class="score-grid">${scoreCard('Original source', 'Synthetic garden-planning document.', data.original)}${scoreCard('Previous live output', 'The existing app result used as the comparison baseline.', data.baseline)}${selected ? scoreCard('Selected research draft', selectedDescription, selected) : '<section class="score-card"><h2>No research draft selected</h2><p>No eligible trial met the stated selection rule. The previous live output remains the baseline.</p></section>'}</div><div class="notice"><p>${escape(data.notice)}</p><p>These are detector estimates, not the percentage of AI-written words. These results concern one passage. Choosing among the trials and disclosed corrections does not establish performance on other writing or other detectors.</p></div><section class="panel"><div class="panel-head"><h2>Every trial, including unsuccessful attempts</h2><p>Lower estimates are shown as measured. Eligibility records source-review and protected-value checks; it is not a detector-pass label.</p></div><div class="table-scroll" role="region" aria-label="Trial measurements; scroll horizontally on small screens" tabindex="0"><table><caption>Fixed Desklib and Vanguard measurements, on a 0–100 scale.</caption><thead><tr><th scope="col">Trial</th><th scope="col">Strategy</th><th scope="col">Writer</th><th scope="col">Starting point</th><th scope="col">Desklib</th><th scope="col">Vanguard</th><th scope="col">Source review</th></tr></thead><tbody>${rows}</tbody></table></div><p class="section-note">Unavailable measurements are kept visible. Rejected or failed attempts cannot win selection, even if a recorded score is lower.</p></section>${repairPanel}<section class="panel"><div class="panel-head"><h2>How this comparison was selected</h2></div><div class="method-body"><p>${escape(data.selection_rule)}</p><p>The models below were used for the experimental writing and source-review process. The two detectors also inform the research selection, so these results are not a separate, unseen validation benchmark.</p></div><div class="model-grid">${(data.models || []).map(model => `<div><strong>${escape(model.name)}</strong><small>${escape(model.model)}</small></div>`).join('')}</div></section><div class="document-grid">${documentCard('Original source', 'The authoritative source for the entire experiment.', data.original, 'original')}${selected ? documentCard('Selected research draft', selectedDescription + '. Locally generated experimental output.', selected, 'selected') : documentCard('Previous live output', 'Shown for reference; no research draft was selected.', data.baseline, 'baseline')}</div><section class="all-texts"><h2>Read all recorded drafts</h2><p>Each trial and any subsequent source-fidelity correction retains its review notes and exact text hash. Rejected drafts are included so the full experiment can be inspected.</p>${trialTexts}</section>`;
  }

  document.addEventListener('click', async event => {
    const opener = event.target.closest('[data-open-trial]');
    if (opener) {
      const details = document.getElementById(trialId(opener.dataset.openTrial));
      if (details) details.open = true;
      return;
    }
    const button = event.target.closest('button[data-action]');
    if (!button || !data) return;
    const entry = ['original', 'baseline', 'selected'].includes(button.dataset.entry) ? data[button.dataset.entry] : null;
    if (!entry || typeof entry.text !== 'string') return;
    if (button.dataset.action === 'copy') {
      try { await navigator.clipboard.writeText(entry.text); notify('Text copied.'); }
      catch { notify('Copy is unavailable in this browser. Use Download TXT instead.'); }
    } else if (button.dataset.action === 'download') {
      const url = URL.createObjectURL(new Blob([entry.text], {type: 'text/plain;charset=utf-8'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = `txtzi-research-${button.dataset.entry}${button.dataset.entry === 'selected' ? '-trial-' + String(entry.id).replace(/[^a-zA-Z0-9_-]/g, '') : ''}.txt`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    }
  });

  fetch('/static/research-ten-trials.json', {cache: 'no-store'})
    .then(response => { if (!response.ok) throw new Error('Results unavailable'); return response.json(); })
    .then(render)
    .catch(() => { results.innerHTML = '<p class="error" role="alert">The research results could not be loaded. Please refresh this page shortly, or return to the <a href="/#demo">live app example</a>.</p>'; });
})();
