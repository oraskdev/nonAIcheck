"""Build a private, self-contained comparison from verified on-disk study evidence.

No provider requests. No text corpus is embedded in this public generator. Selection is
recomputed from exact-text detector receipts and two independent complete source audits.
The output is deliberately refused inside the repository/public web tree.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.research.recovery import DESK_REV, VANG_REV, validate_score

DETECTORS = (('desklib', DESK_REV), ('vanguard', VANG_REV))
WHOLE_CHECKS = ('unsupported_additions', 'qualification_or_uncertainty_loss', 'causality_changes', 'quality_issues')


def read(path):
    return json.loads(Path(path).read_text())


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def esc(value):
    return html.escape(str(value), quote=True)


def exact_score(value):
    return format(Decimal(str(value)) * 100, 'f')


def approvals(reviews, digest, source_hash, expected_ids):
    accepted = {}
    for path, item in reviews:
        rows = item.get('claim_results', [])
        reviewer = item.get('reviewer')
        whole = item.get('whole_source_review', {})
        if (item.get('sha256') == digest and item.get('source_sha256') == source_hash
            and item.get('eligible') is True and item.get('issues') == []
            and item.get('reviewed_blind_to_scores') is True
            and isinstance(reviewer, str) and reviewer.strip()
            and len(rows) == len(expected_ids) and {r.get('id') for r in rows} == expected_ids
            and all(r.get('status') in ('preserved', 'pass') and isinstance(r.get('reason'), str) and r['reason'].strip() for r in rows)
            and isinstance(whole, dict) and all(whole.get(k) is False for k in WHOLE_CHECKS)):
            accepted.setdefault(reviewer, {'file': path.name, 'review': item})
    return list(accepted.values())


def load_pair(run, digest):
    paths = {d: run / 'scores' / d / (digest + '.json') for d, _ in DETECTORS}
    if not all(path.exists() for path in paths.values()):
        return None
    receipts = {d: read(paths[d]) for d, _ in DETECTORS}
    for detector, revision in DETECTORS:
        validate_score(receipts[detector], digest, detector, revision)
    return receipts


def original_receipts(run, source):
    pair = load_pair(run, sha(source))
    if pair is None:
        raise ValueError('Fresh exact-text source measurements are required from both current pinned detectors')
    return pair, 'Current study reference measurements on the exact original text. The source reference is excluded from generated candidate counts.'


def end_to_end(run, source):
    runs = []
    for path in sorted(run.glob('production-e2e-*/result.json')):
        data = read(path)
        report = data['report']
        fulltext = '\n\n'.join(b['text'] for b in data['blocks'])
        if (path.parent / 'source.txt').read_text() != source or (path.parent / 'output.txt').read_text() != fulltext:
            raise ValueError('End-to-end source/output file mismatch')
        attempts = report['detector_comparison']['attempts']
        matching = [a for a in attempts if a['text_sha256'] == sha(fulltext)]
        if not matching:
            raise ValueError('End-to-end final text lacks a matching exact-hash assessment')
        measurement = matching[-1]['assessment']
        validate_score({'sha256': sha(fulltext), 'revision': DESK_REV, 'measurement': measurement}, sha(fulltext), 'desklib', DESK_REV)
        if report['after_detector'] != measurement:
            raise ValueError('End-to-end selected score disagrees with the final output')
        usage = report.get('provider_usage', [])
        workflow = report.get('bounded_workflow', {})
        runs.append({'id': path.parent.name, 'source_sha256': sha(source), 'output_sha256': sha(fulltext),
            'score': measurement['ai_score'], 'original_retained': fulltext == source, 'attempts': len(attempts),
            'provider_calls': len(usage), 'providers': sorted({x['provider'] for x in usage}),
            'elapsed_seconds': workflow.get('elapsed_seconds'), 'cost': workflow.get('estimated_or_reserved_usd'),
            'writing_method': report.get('writing_method'), 'flags': report.get('flags', [])})
    return runs



def phase_b_jobs(run):
    folder = run / 'phase-b'
    paths = sorted((folder / 'jobs').glob('*.json'))
    if not paths:
        return []
    protocol = read(folder / 'protocol.json')
    approval = protocol.get('approval', {})
    banks = protocol.get('frozen_banks', [])
    if (protocol.get('status') != 'activated' or protocol.get('phase') != 'B'
        or protocol.get('new_api_calls') != 0 or approval.get('authorized') is not True
        or approval.get('phase') != 'B' or approval.get('max_new_unique') != 1000
        or len(banks) != 2 or len(set(banks)) != 2 or approval.get('banks') != banks
        or len(paths) > 1000):
        raise ValueError('Phase B is not bound to a valid separate activation')
    expected_files = {f'{bank}-{suffix}.json' for bank in banks for suffix in ('bank', 'review', 'grok.request', 'grok.response')}
    bindings = protocol.get('frozen_bank_file_sha256', {})
    if set(bindings) != expected_files:
        raise ValueError('Phase B frozen bank bindings are incomplete')
    for name, digest in bindings.items():
        if sha((run / 'rounds' / name).read_text()) != digest:
            raise ValueError('Phase B frozen bank evidence changed')
    bank_data = {bank: read(run / 'rounds' / (bank + '-bank.json')) for bank in banks}
    jobs = []
    for path in paths:
        job = read(path)
        if job.get('phase') != 'B' or job.get('bank') not in banks or job.get('prediction_is_not_a_measurement') is not True:
            raise ValueError('Phase B candidate lacks phase/bank identity')
        bank = bank_data[job['bank']]
        if job.get('parent_id') != bank['parent']['id'] or job.get('parent_sha256') != bank['parent']['sha256']:
            raise ValueError('Phase B candidate parent differs from its frozen bank')
        patches = {p['id']: p for p in bank['patches']}
        ids = job.get('patch_ids', [])
        if not ids or len(ids) != len(set(ids)) or any(i not in patches for i in ids):
            raise ValueError('Phase B candidate patch identities are invalid')
        chosen = sorted((patches[i] for i in ids), key=lambda p: p['start'])
        if any(a['end'] > b['start'] for a, b in zip(chosen, chosen[1:])):
            raise ValueError('Phase B candidate contains overlapping patches')
        text = bank['parent']['text']
        for patch in reversed(chosen):
            if text[patch['start']:patch['end']] != patch['find']:
                raise ValueError('Phase B exact patch span differs')
            text = text[:patch['start']] + patch['replace'] + text[patch['end']:]
        if text != job['text']:
            raise ValueError('Phase B full text differs from its frozen patch combination')
        jobs.append(job)
    return jobs

def build_data(run, production_commit=None):
    run = Path(run)
    protocol = read(run / 'protocol.json')
    source = (run / 'source.txt').read_text()
    source_hash = sha(source)
    claims = read(run / 'claims.json')
    bindings = read(run / 'source-bindings.json')
    ids = {f'G{i:02d}' for i in range(1, 33)}
    if (source_hash != protocol['source_sha256'] or len(claims) != 32 or {x['id'] for x in claims} != ids
        or bindings.get('source_sha256') != source_hash or bindings.get('claims_sha256') != sha(json.dumps(claims, sort_keys=True))
        or bindings.get('initial_parent_sha256') != protocol['initial_parent']['sha256']):
        raise ValueError('Source/checklist binding differs from the immutable protocol')
    for detector, revision in DETECTORS:
        if protocol['detectors'][detector]['revision'] != revision:
            raise ValueError('Protocol detector revision changed')
    if production_commit and not re.fullmatch(r'[a-f0-9]{7,40}', production_commit):
        raise ValueError('Production commit must be a hexadecimal Git revision')
    reviews = [(p, read(p)) for p in sorted((run / 'reviews').glob('*.json'))]
    phase_a = [read(p) for p in sorted((run / 'jobs').glob('*.json'))]
    phase_b = phase_b_jobs(run)
    if phase_b and ({j['sha256'] for j in phase_a} & {j['sha256'] for j in phase_b} or len({j['sha256'] for j in phase_a}) != 1000):
        raise ValueError('Phase B requires 1000 distinct phase A texts and no duplicate text across phases')
    jobs = phase_a + phase_b
    phases = {job['id']: phase for phase, items in [('A', phase_a), ('B', phase_b)] for job in items}
    baseline = read(run / 'baseline.json')
    by_hash, by_id = {}, {}
    for item in [baseline] + jobs:
        if sha(item['text']) != item['sha256'] or item['source_sha256'] != source_hash:
            raise ValueError('Candidate text/source hash mismatch: ' + item['id'])
        if item['id'] in by_id and by_id[item['id']] != item:
            raise ValueError('Duplicate candidate ID with different content')
        by_id[item['id']] = item
        by_hash.setdefault(item['sha256'], item)
    if baseline['sha256'] != protocol['initial_parent']['sha256']:
        raise ValueError('Initial parent changed')
    def lineage(item):
        chain, seen = [], set()
        while item['id'] != baseline['id']:
            if item['id'] in seen:
                raise ValueError('Cyclic candidate lineage')
            seen.add(item['id']); chain.append(item['id'])
            parent = by_id.get(item.get('parent_id'))
            if not parent or item.get('parent_sha256') != parent['sha256']:
                raise ValueError('Candidate parent hash mismatch')
            item = parent
        return [baseline['id']] + list(reversed(chain))
    paired, eligible = [], []
    for digest, job in by_hash.items():
        if digest == baseline['sha256'] or digest == source_hash:
            continue
        pair = load_pair(run, digest)
        if pair is None:
            continue
        chain = lineage(job)
        audit = approvals(reviews, digest, source_hash, ids)
        scores = {d: pair[d]['measurement']['ai_score'] for d, _ in DETECTORS}
        item = {'phase': phases[job['id']], 'job': job, 'scores': scores, 'maximum': max(scores.values()), 'receipts': pair, 'approvals': audit, 'lineage': chain}
        paired.append(item)
        if len(audit) >= 2:
            eligible.append(item)
    if phase_b and sum(item['phase'] == 'A' for item in paired) != 1000:
        raise ValueError('Phase B cannot be reported before phase A has 1000 paired measurements')
    eligible.sort(key=lambda x: (x['maximum'], x['scores']['desklib'] + x['scores']['vanguard'], x['job']['id']))
    if not eligible:
        raise ValueError('No candidate has two independent complete reviews and paired exact-text scores')
    selected = eligible[0]
    source_pair, source_note = original_receipts(run, source)
    ledger = read(run / 'ledger.json')
    requests = ledger['requests']
    estimate = sum(Decimal(str(x.get('actual_usd', x['reserved_usd']))) for x in requests.values())
    completed = [x for x in requests.values() if x.get('status') == 'response_saved' and 'actual_usd' in x]
    rounds = [read(p) for p in sorted((run / 'rounds').glob('*-complete.json'))]
    return {'checkpoint_at': datetime.now(timezone.utc).isoformat(), 'source': source, 'source_sha256': source_hash,
        'original_receipts': source_pair, 'original_note': source_note, 'selected': selected,
        'phase_counts': [{'phase': phase, 'unique': len({j['sha256'] for j in items} - {source_hash, baseline['sha256']}), 'paired': sum(item['phase'] == phase for item in paired), 'reviewed': sum(item['phase'] == phase for item in eligible), 'new_provider_requests': len(requests) if phase == 'A' else 0} for phase, items in [('A', phase_a), ('B', phase_b)] if items],
        'unique_candidates': len({j['sha256'] for j in jobs} - {source_hash, baseline['sha256']}), 'paired_candidates': len(paired), 'reviewed_candidates': len(eligible),
        'thresholds': {str(n): any(item['maximum'] < n / 100 for item in eligible) for n in (30, 10, 2)},
        'provider_requests': len(requests), 'completed_provider_calls': len(completed), 'unknown_cost_requests': len(requests) - len(completed),
        'completed_patch_banks': sum(x.get('status') == 'generated' for x in rounds), 'estimated_or_reserved_usd': str(estimate),
        'cost_limit_usd': ledger['limit_usd'], 'protocol': protocol, 'production_commit': production_commit,
        'end_to_end': end_to_end(run, source)}


CSS = '''
:root{color-scheme:light;--ink:#17263a;--muted:#627069;--green:#237357;--mint:#d9efe3;--paper:#fff;--line:#dae3dd}*{box-sizing:border-box}body{margin:0;background:#f2f5f1;color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:#176c50}button{font:inherit;cursor:pointer}header{background:#122537;color:white;padding:38px max(24px,calc((100vw - 1220px)/2));position:relative;overflow:hidden}header:after{content:"";width:350px;height:350px;border:1px solid #83b7a14a;border-radius:50%;position:absolute;right:-100px;top:-145px;box-shadow:0 0 0 55px #73ad9830,0 0 0 110px #73ad9810;pointer-events:none}.brand{font-size:34px;font-weight:780;letter-spacing:-2px;display:flex;align-items:center;gap:14px}.brand img{width:180px;height:56px;object-fit:contain}.brand .logo-print{display:none}.eyebrow{letter-spacing:2.5px;text-transform:uppercase;font-size:10px;font-weight:750;color:#a9cdb8}header h1{font-size:clamp(32px,5vw,58px);letter-spacing:-2px;line-height:1.08;max-width:840px;margin:34px 0 20px}header p{max-width:740px;color:#c0d0cf;font-size:16px}.meta{font-size:11px;color:#a8bcbe;margin-top:27px}main{max-width:1270px;margin:auto;padding:32px 24px 60px}.summary{display:grid;grid-template-columns:1.15fr 1fr;gap:24px;margin-bottom:27px}.card{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:26px;box-shadow:0 7px 25px #17342505}.label{text-transform:uppercase;letter-spacing:1.7px;font-size:10px;color:var(--muted);font-weight:750}.metric-pair{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:15px 0}.metric strong{display:block;font-size:47px;letter-spacing:-2px;line-height:1.1;color:var(--green)}.metric small{color:var(--muted)}.muted{color:var(--muted)}.fine{font-size:12px;color:var(--muted);line-height:1.7}.pill{display:inline-block;border:1px solid #ccded2;background:#ecf6ef;color:#236649;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:650}.pill.pending{background:#f5f4ef;border-color:#e2dfd1;color:#796c47}.targets{display:flex;flex-wrap:wrap;gap:8px;margin:17px 0}h2{font-size:26px;letter-spacing:-.8px;line-height:1.25;margin:0 0 15px}h3{font-size:17px;letter-spacing:-.3px;margin:0 0 14px}.notice{background:#e6efe9;border-left:3px solid #4c9673;border-radius:0 10px 10px 0;padding:17px 21px;color:#3e584c;margin:22px 0}.counts{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:13px;overflow:hidden;margin:25px 0}.counts>div{background:white;padding:18px 22px}.counts strong{font-size:27px;display:block;letter-spacing:-1px}.counts span{font-size:11px;color:var(--muted)}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:38px 0 18px}.section-heading p{margin:0;max-width:540px;font-size:13px;color:var(--muted)}.compare{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}.document{background:white;border:1px solid var(--line);border-radius:15px;overflow:hidden}.doc-head{padding:22px 25px;border-bottom:1px solid var(--line);background:#fafbf8}.doc-head h3{margin:4px 0 8px}.doc-head .label{color:#617666}.score-line{display:flex;gap:20px;font-size:12px;color:var(--muted);flex-wrap:wrap}.score-line strong{color:var(--ink)}.tools{display:flex;gap:8px;margin-top:15px}.tools button,.print{background:transparent;color:#276146;border:1px solid #ccddd0;padding:7px 11px;border-radius:7px;font-size:11px}.tools button:hover{background:#e7f1e9}.document pre{font:15px/1.9 Georgia,"Times New Roman",serif;color:#303e36;white-space:pre-wrap;word-break:normal;overflow-wrap:anywhere;margin:0;padding:28px 27px}.hash{font:10px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere;color:#6c7c72;padding:0 25px 20px}.two-column{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:25px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:12px 9px;border-bottom:1px solid #e6ece6;vertical-align:top}th{font-size:10px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);background:#f6f8f3}td code{font-size:10px;word-break:break-all}.nowrap{white-space:nowrap}details{background:white;border:1px solid var(--line);border-radius:12px;margin-top:20px;padding:18px 23px}summary{font-size:14px;font-weight:650;cursor:pointer}details>div{padding-top:16px}.checklist{columns:2;column-gap:30px;font-size:12px;color:#56695d;margin:0;padding-left:20px}.checklist li{break-inside:avoid;margin-bottom:10px}.audit-note{border-bottom:1px solid #e0e8df;padding:12px 0}.audit-note p{font-size:12px;margin:4px 0;color:#607269}.audit-note code{font-size:11px}.status{min-height:24px;text-align:center;font-size:12px;color:#276347}.footer{font-size:11px;color:#7c887f;border-top:1px solid var(--line);margin-top:30px;padding-top:20px;display:flex;justify-content:space-between;gap:20px}ul{padding-left:20px}.footer button{flex-shrink:0}a:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #5d9a79;outline-offset:3px}@media(max-width:900px){.summary,.two-column{grid-template-columns:1fr}.counts{grid-template-columns:1fr 1fr}.compare{gap:14px}.document pre{font-size:14px;padding:22px}.checklist{columns:1}}@media(max-width:650px){header{padding:25px 22px}.brand{font-size:30px}header h1{letter-spacing:-1.3px;margin-top:25px}main{padding:22px 15px 40px}.compare{grid-template-columns:1fr}.card{padding:22px}.counts>div{padding:16px}.section-heading{display:block}.section-heading p{margin-top:12px}.metric strong{font-size:43px}.doc-head{padding:20px}.footer{display:block}.footer button{margin-top:14px}}@media(prefers-reduced-motion:reduce){*{animation:none!important;scroll-behavior:auto!important;transition:none!important}}@media print{.brand .logo-screen{display:none}.brand .logo-print{display:block}body{background:white;font-size:11px}header{background:white!important;color:#17263a;padding:0 0 20px}header:after{display:none}header p,.meta,.eyebrow{color:#516459}header h1{font-size:30px;margin:15px 0}main{max-width:none;padding:0}.card,.document,details{box-shadow:none;border-color:#bbb}.compare,.summary,.two-column{display:block}.card,.document{margin-bottom:20px;break-inside:avoid}.document pre{font-size:11px;padding:18px}.tools,.print,.status{display:none}.counts{grid-template-columns:repeat(4,1fr)}.metric strong{font-size:30px}.section-heading{margin-top:24px}details{break-inside:avoid}details>div{display:block}.hash{font-size:8px}a{color:inherit;text-decoration:none}@page{margin:17mm}}
'''

JS = '''document.addEventListener('click', async event => {
  const button=event.target.closest('button[data-text]');
  if(!button)return;
  const text=document.getElementById(button.dataset.text).textContent;
  const status=document.getElementById('action-status');
  if(button.dataset.action==='download'){
    const blob=new Blob([text],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=button.dataset.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='Text download prepared.';return;
  }
  try{await navigator.clipboard.writeText(text);status.textContent='Exact text copied.';}
  catch{const selection=window.getSelection();const range=document.createRange();range.selectNodeContents(document.getElementById(button.dataset.text));selection.removeAllRanges();selection.addRange(range);status.textContent='Text selected. Use your device’s Copy command.';}
});document.getElementById('print-report').addEventListener('click',()=>window.print());'''


def document_panel(title, text_id, text, digest, scores, subtitle):
    return f'''<article class="document"><div class="doc-head"><span class="label">{esc(subtitle)}</span><h3>{esc(title)}</h3><div class="score-line"><span>Desklib <strong>{scores['desklib'] * 100:.2f}</strong> / 100</span><span>Vanguard <strong>{scores['vanguard'] * 100:.2f}</strong> / 100</span></div><div class="tools"><button data-text="{text_id}">Copy full text</button><button data-text="{text_id}" data-action="download" data-filename="txtzi-{text_id}.txt">Download TXT</button></div></div><pre id="{text_id}">{esc(text)}</pre><div class="hash">SHA-256 · {esc(digest)}</div></article>'''


def render(data):
    logo = base64.b64encode((ROOT / 'static/txtzi-logo.svg').read_bytes()).decode()
    dark_logo = base64.b64encode((ROOT / 'static/txtzi-logo-dark.svg').read_bytes()).decode()
    brand = f'<img class="logo-screen" src="data:image/svg+xml;base64,{dark_logo}" width="180" height="56" alt="txtzi"><img class="logo-print" src="data:image/svg+xml;base64,{logo}" width="180" height="56" alt="txtzi">'
    selected = data['selected']; job = selected['job']; scores = selected['scores']
    original_scores = {d: data['original_receipts'][d]['measurement']['ai_score'] for d, _ in DETECTORS}
    thresholds = ''.join(f'<span class="pill{("" if passed else " pending")}">Both below {target}: {"verified" if passed else "not reached"}</span>' for target, passed in data['thresholds'].items())
    exact_rows = ''.join(f'<tr><td>{d.title()}</td><td class="nowrap">{exact_score(original_scores[d])}</td><td class="nowrap">{exact_score(scores[d])}</td></tr>' for d, _ in DETECTORS)
    phase_rows = ''.join(f'<tr><td>Phase {row["phase"]}</td><td>{row["unique"]:,}</td><td>{row["paired"]:,}</td><td>{row["reviewed"]:,}</td><td>{row["new_provider_requests"]}</td></tr>' for row in data['phase_counts'])
    phase_table = f'<div class="table-wrap"><table><thead><tr><th>Study phase</th><th>Distinct candidates</th><th>Paired measurements</th><th>Two approvals</th><th>New provider requests</th></tr></thead><tbody>{phase_rows}</tbody></table></div>'
    phase_note = 'Phase B reuses frozen, reviewed patch banks from phase A with no new writing API calls. Predicted ranks only choose combinations to test; every displayed result comes from new exact-text detector inference.' if len(data['phase_counts']) > 1 else 'Phase B is not included in this checkpoint.'
    audit_details = ''.join(f'<div class="audit-note"><strong>Independent review {i}</strong><p><code>{esc(a["review"]["reviewer"])}</code></p><p>{esc(a["review"]["whole_source_review"].get("assessment", "All whole-source checks passed."))}</p><p>32 / 32 source claims preserved · reviewed blind to scores · no reported issues</p></div>' for i, a in enumerate(selected['approvals'], 1))
    claims = ''.join(f'<li><strong>{esc(row["id"])}</strong> {esc(row["reason"])}</li>' for row in selected['approvals'][0]['review']['claim_results'])
    pin_rows = ''.join(f'<tr><td>{d.title()}</td><td>{esc(data["protocol"]["detectors"][d]["model"])}</td><td><code>{rev}</code></td></tr>' for d, rev in DETECTORS)
    e2e_rows = ''.join(f'<tr><td>{esc(r["id"])}</td><td>{exact_score(r["score"])}</td><td>{r["provider_calls"]}</td><td>{r["attempts"]}</td><td>{esc(r["elapsed_seconds"])} s</td><td>{"Original retained after an incomplete meaning inventory" if r["original_retained"] else "Completed; target performance not reached"}</td></tr>' for r in data['end_to_end'])
    e2e = f'<div class="table-wrap"><table><thead><tr><th>Prototype run</th><th>Final Desklib / 100</th><th>Provider calls</th><th>Measured texts</th><th>Duration</th><th>Outcome</th></tr></thead><tbody>{e2e_rows}</tbody></table></div>' if data['end_to_end'] else '<p>No completed end-to-end prototype records were available at this checkpoint.</p>'
    commit = esc(data['production_commit'] or 'Not supplied for this checkpoint')
    embedded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>txtzi — Private test comparison</title><style>{CSS}</style></head><body><header><div class="brand">{brand}</div><div class="eyebrow">Private research checkpoint · one English source</div><h1>Better wording.<br>Measured with context.</h1><p>Your original text and the strongest fully reviewed draft in the preserved recovery study. Every displayed research result is tied to the exact text, two detector receipts and independent source reviews.</p><div class="meta">Prepared {esc(data['checkpoint_at'])} · No external resources or live API calls are needed to read this file.</div></header><main><section class="summary"><div class="card"><span class="label">Best verified research draft · phase {esc(selected['phase'])} · {esc(job['id'])}</span><div class="metric-pair"><div class="metric"><strong>{scores['desklib'] * 100:.2f}</strong><small>Desklib / 100</small></div><div class="metric"><strong>{scores['vanguard'] * 100:.2f}</strong><small>Vanguard / 100</small></div></div><span class="pill">Two independent complete source approvals</span><p class="fine">Cards round to two decimals. Exact stored values appear below. These are uncalibrated model estimates, not percentages of AI-written words or proof of authorship.</p></div><div class="card"><span class="label">Your requested thresholds</span><h2>Both detectors must qualify.</h2><div class="targets">{thresholds}</div><p class="fine">A target is marked verified only when the same full text scores strictly below it on both fixed models and has two distinct, complete source approvals. Lower-scoring unaudited candidates are never promoted here.</p></div></section><div class="notice"><strong>This is a research result, not the current app output.</strong> Both detectors were used repeatedly to choose changes to this one synthetic source. There is no held-out detector or independent-document success rate. This does not establish reliable bypass of other checkers or removal of statistical watermarks.</div><section class="counts" aria-label="Current study counts"><div><strong>{data['unique_candidates']:,}</strong><span>Distinct generated candidate texts</span></div><div><strong>{data['paired_candidates']:,}</strong><span>Candidates scored by both models</span></div><div><strong>{data['reviewed_candidates']:,}</strong><span>Paired candidates with two full approvals</span></div><div><strong>{data['completed_patch_banks']:,}</strong><span>Completed shared three-provider patch banks</span></div></section><p class="fine">Counts cover the rebuilt study only. Original and starting-reference texts are excluded. A patch bank combines Claude, OpenAI and Grok work into many distinct variants; these are not {data['unique_candidates']:,} independent three-model end-to-end rewrites. Earlier lost runs are not counted.</p>{phase_table}<p class="fine">{phase_note}</p><section><div class="section-heading"><div><span class="label">Full text comparison</span><h2>Your source. The reviewed result.</h2></div><p>Copy or download either exact text. All paragraphs and the title are included; no text is shortened for this comparison.</p></div><div class="compare">{document_panel('Original source','original',data['source'],data['source_sha256'],original_scores,'Before · immutable synthetic source')}{document_panel('Selected research draft','selected',job['text'],job['sha256'],scores,'After · two complete independent reviews')}</div><div class="status" id="action-status" role="status" aria-live="polite"></div></section><section class="two-column"><div class="card"><h3>Exact measurements out of 100</h3><div class="table-wrap"><table><thead><tr><th>Detector</th><th>Original</th><th>Selected</th></tr></thead><tbody>{exact_rows}</tbody></table></div><p class="fine">{esc(data['original_note'])}</p><p class="fine">Each selected score covers the full candidate text and matches its SHA-256. Selection minimizes the larger of the two scores among candidates that pass both independent reviews.</p></div><div class="card"><h3>Calls, cost and lineage</h3><p><strong>{data['provider_requests']}</strong> provider requests recorded; <strong>{data['completed_provider_calls']}</strong> have returned usage and estimated costs. <strong>{data['unknown_cost_requests']}</strong> retain a conservative reservation.</p><p><strong>${esc(data['estimated_or_reserved_usd'])}</strong> estimated or reserved research API cost, within a <strong>${esc(data['cost_limit_usd'])}</strong> phase cap.</p><p class="fine">This is not an invoice. Hosting and separate end-to-end validation costs are excluded. Shared patch banks and unresolved charges remain counted.</p><p class="fine"><strong>Selected lineage:</strong><br>{esc(' → '.join(selected['lineage']))}</p></div></section><section class="card" style="margin-top:25px"><span class="label">Production readiness</span><h2>The app and the experiment remain separate.</h2><p>The published application remains on its <strong>meaning-first-v2</strong> workflow. The bounded prototype was tested independently from the full original; it did not achieve the requested performance target and has not replaced that default.</p>{e2e}<p class="fine">The bounded prototype’s tiny score change is not equivalent to this adaptive study’s best result. Its successful complete run uses all three writing providers; the earlier stopped run did not. Only Desklib guides that prototype, so a second-detector target is not established by these app-style runs.</p><p class="fine"><strong>Production commit recorded by the operator:</strong> <code>{commit}</code></p></section><details><summary>Source-review evidence · all 32 claims</summary><div>{audit_details}<ol class="checklist">{claims}</ol><p class="fine">Reviewer identities are recorded agent IDs. “Independent” here means separate reviews of the full source and candidate, blind to the candidate scores; it does not mean external human certification.</p></div></details><details><summary>Detector versions and reproducibility</summary><div class="table-wrap"><table><thead><tr><th>Detector</th><th>Model</th><th>Pinned revision</th></tr></thead><tbody>{pin_rows}</tbody></table><p class="fine">Selected-candidate settings: Desklib uses 512-token windows with 64-token overlap, bfloat16 matrix storage and float32 compute. Vanguard uses float32, SDPA, reference compilation disabled, no truncation and a maximum 8,192 tokens. Exact hashes bind the source, candidate and score receipts. This file includes the selected receipts and reviews as inert JSON for inspection.</p></div></details><footer class="footer"><span>txtzi · Private owner report · Generated from preserved evidence at the stated checkpoint.<br>No authorship guarantee, universal detector-pass claim or watermark-removal certification.</span><button class="print" id="print-report">Print / Save as PDF</button></footer></main><script type="application/json" id="report-evidence">{embedded}</script><script>{JS}</script></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=ROOT / 'test-artifacts/recovery-oct4')
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'txtzi-test-results.html')
    parser.add_argument('--production-commit')
    args = parser.parse_args(argv)
    if args.output.resolve().is_relative_to(ROOT):
        raise ValueError('Private output must be outside the Git/public web repository')
    data = build_data(args.run, args.production_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.html.tmp')
    temporary.write_text(render(data))
    temporary.replace(args.output)
    print(json.dumps({'output': str(args.output), 'checkpoint_at': data['checkpoint_at'], 'selected_id': data['selected']['job']['id'], 'sha256': data['selected']['job']['sha256'], 'scores': data['selected']['scores'], 'thresholds': data['thresholds'], 'paired': data['paired_candidates'], 'unique': data['unique_candidates']}))


if __name__ == '__main__':
    main()
