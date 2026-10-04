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




HOLDOUT_FILES = {'app/bounded_patch.py', 'app/bounded_draft.py', 'app/providers.py', 'app/pipeline.py', 'app/hygiene.py', 'app/local_detector.py', 'app/config.py', 'tests/test_bounded_patch.py', 'tests/test_bounded_draft.py', 'tests/test_bounded_audit.py'}


def holdout_data(run, code_root=ROOT):
    folder = run / 'production-holdout-01'
    if not (folder / 'result.json').exists():
        return None
    frozen = read(folder / 'frozen-protocol.json')
    start = read(folder / 'attempt-started.json')
    source_meta = read(folder / 'source.json')
    result = read(folder / 'result.json')
    source = (folder / 'source.txt').read_text()
    output = (folder / 'output.txt').read_text()
    source_hash, output_hash = sha(source), sha(output)
    mapping = frozen.get('files', {})
    if (set(mapping) != HOLDOUT_FILES or sha(json.dumps(mapping, sort_keys=True, separators=(',', ':'))) != frozen.get('strategy_sha256')
        or any(hashlib.sha256((code_root / name).read_bytes()).hexdigest() != digest for name, digest in mapping.items())
        or start.get('strategy_sha256') != frozen['strategy_sha256']):
        raise ValueError('Holdout frozen strategy or implementation binding changed')
    expected_gate = {'full_source_review_approved': True, 'desklib_output_strictly_below': .3, 'desklib_absolute_reduction_at_least': .1}
    if (frozen.get('workflow') != 'bounded-draft-v1' or frozen.get('quote_enablement') is not False
        or frozen.get('no_prompt_retuning_after_input') is not True or frozen.get('attempts_allowed') != 1
        or frozen.get('selection_detector') != 'Desklib only'
        or frozen.get('independent_postselection_detector') != 'Vanguard original and chosen output; never candidate selection'
        or frozen.get('prospective_gate') != expected_gate
        or frozen.get('detector_revisions') != dict(DETECTORS)):
        raise ValueError('Holdout frozen gate, detector or disabled-mode metadata differs')
    blocks = read(folder / 'source-blocks.json')
    blind = read(folder / 'blind-source-review-input.json')
    if (source_hash != source_meta.get('text_sha256') or source_hash != start.get('source_sha256')
        or source_meta.get('synthetic') is not True or source_meta.get('blocks') != blocks
        or '\n\n'.join(b['text'] for b in blocks) != source
        or '\n\n'.join(b['text'] for b in result['blocks']) != output
        or blind.get('original') != blocks or blind.get('candidate') != result['blocks']
        or blind.get('source_sha256') != source_hash or blind.get('candidate_sha256') != output_hash
        or len(source.split()) != start.get('source_words') or len(source.split()) != source_meta.get('word_count')):
        raise ValueError('Holdout exact source/output identity differs')
    inv_path = folder / 'independent-source-inventory.json'
    inventory = read(inv_path)
    review = read(folder / 'independent-final-review.json')
    ids = {f'H{i:02d}' for i in range(1, 49)}
    claims = inventory.get('claims', [])
    rows = review.get('claim_results', [])
    whole = review.get('whole_source_review', {})
    reverse = review.get('reverse_candidate_support', [])
    body_ids = {b['id'] for b in result['blocks'] if b['type'] != 'heading'}
    candidate_by_id = {b['id']: b for b in result['blocks']}
    source_by_id = {b['id']: b for b in blocks}
    claim_by_id = {c['id']: c for c in claims}
    if (inventory.get('source_sha256') != source_hash or inventory.get('created_before_viewing_output') is not True
        or inventory.get('claim_count') != 48 or len(claims) != 48 or set(claim_by_id) != ids
        or review.get('inventory_file_sha256') != sha(inv_path.read_text())
        or review.get('source_sha256') != source_hash or review.get('candidate_sha256') != output_hash or review.get('sha256') != output_hash
        or not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()
        or review.get('reviewed_blind_to_scores') is not True or review.get('independently_derived_inventory_before_output') is not True
        or review.get('claim_count') != 48 or review.get('eligible') is not True or review.get('verdict') != 'pass'
        or review.get('edits_made') is not False or review.get('issues') != []
        or review.get('bidirectional_review_complete') is not True or review.get('title_exactly_preserved') is not True
        or review.get('protected_numeric_multiset_preserved') is not True
        or len(review.get('checked_claim_ids', [])) != 48 or set(review['checked_claim_ids']) != ids
        or len(rows) != 48 or {r.get('id') for r in rows} != ids
        or not isinstance(whole, dict) or any(whole.get(k) is not False for k in WHOLE_CHECKS)
        or len(reverse) != len(body_ids) or {r.get('candidate_block') for r in reverse} != body_ids
        or any(r.get('status') != 'supported' or r.get('unsupported_claims') != [] or not r.get('supported_by_claim_ids') or not set(r['supported_by_claim_ids']).issubset(ids) for r in reverse)):
        raise ValueError('Holdout independent full-source review binding is incomplete or failed')
    for row in rows:
        claim = claim_by_id[row['id']]
        candidate = candidate_by_id.get(row.get('candidate_block'), {})
        if (row.get('status') != 'preserved' or not row.get('reason') or row.get('source_claim') != claim['statement']
            or row.get('source_block') != claim['source_block'] or row.get('source_block') not in source_by_id
            or not row.get('candidate_evidence') or row['candidate_evidence'] not in candidate.get('text', '')):
            raise ValueError('Holdout claim or candidate-evidence identity differs')
    report = result['report']
    final_event = read(folder / '018-result.json')
    if final_event.get('event') != 'result' or final_event.get('blocks') != result['blocks'] or final_event.get('report') != report:
        raise ValueError('Holdout completion record does not match the result')
    timeline = [frozen['created_at'], source_meta['authored_at'], inventory['created_at'], start['at'], final_event['recorded_at'], review['reviewed_at']]
    times = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in timeline]
    if times != sorted(times):
        raise ValueError('Holdout strategy/source/inventory/run/review chronology differs')
    comparison = report['detector_comparison']
    attempts = comparison['attempts']
    original_attempt = [a for a in attempts if a.get('version') == 'original' and a.get('text_sha256') == source_hash]
    selected_attempt = [a for a in attempts if a.get('version') == comparison['selected_version'] and a.get('text_sha256') == output_hash]
    if len(original_attempt) != 1 or len(selected_attempt) != 1:
        raise ValueError('Holdout selected/original exact-text assessment is missing')
    before, after = original_attempt[0]['assessment'], selected_attempt[0]['assessment']
    if report.get('before_detector') != before or report.get('after_detector') != after or report.get('writing_method') != frozen['workflow']:
        raise ValueError('Holdout report differs from its selected exact-text assessment')
    for digest, measurement in [(source_hash, before), (output_hash, after)]:
        validate_score({'sha256':digest, 'revision':DESK_REV, 'measurement':measurement}, digest, 'desklib', DESK_REV)
    pair = {label: {'desklib': {'sha256':digest, 'revision':DESK_REV, 'measurement':measurement}, 'vanguard':read(folder / f'vanguard-{name}.json')}
        for label, digest, measurement, name in [('original', source_hash, before, 'original'), ('output', output_hash, after, 'output')]}
    for label, receipts in pair.items():
        receipt = receipts['vanguard']
        validate_score(receipt, source_hash if label == 'original' else output_hash, 'vanguard', VANG_REV)
        if (receipt.get('excluded_from_research_phase_counts') is not True
            or receipt.get('purpose') != 'Held-out production E2E evaluation only; never used for selection or retuning'
            or datetime.fromisoformat(receipt['measured_at']) <= times[-2]):
            raise ValueError('Holdout Vanguard is not bound to postselection evaluation')
    completed = [read(path) for path in sorted(folder.glob('*-provider_completed.json'))]
    usage = report.get('provider_usage', [])
    if (len(completed) != len(usage) or {r.get('provider') for r in usage} != {'anthropic', 'openai', 'xai'}
        or len(completed) > frozen['max_new_calls'] or len(attempts) > frozen['max_assessments']):
        raise ValueError('Holdout completed provider calls or assessment budget differs')
    for event, item in zip(completed, usage):
        if (event.get('event') != 'provider_completed' or event.get('status') != 'completed'
            or event.get('model') != frozen['models'].get(event.get('provider'))
            or event.get('request_sha256') != sha(event['model'] + event['system'] + event['prompt'])
            or not isinstance(event.get('raw_output'), str) or not event['raw_output']
            or any(event.get(key) != value for key, value in item.items())
            or any(event.get(key) != event.get('usage', {}).get(key) for key in ('input_tokens', 'output_tokens'))):
            raise ValueError('Holdout provider usage is not bound to completed request evidence')
    workflow = report['bounded_workflow']
    cost = sum(Decimal(str(u['charged_or_reserved_usd'])) for u in usage)
    if cost != Decimal(str(workflow['estimated_or_reserved_usd'])) or cost > Decimal(str(frozen['max_estimated_or_reserved_api_usd'])):
        raise ValueError('Holdout API accounting does not match its frozen budget')
    reduction = before['ai_score'] - after['ai_score']
    passed = after['ai_score'] < expected_gate['desklib_output_strictly_below'] and reduction >= expected_gate['desklib_absolute_reduction_at_least']
    return {'id':folder.name, 'source':source, 'output':output, 'source_sha256':source_hash, 'output_sha256':output_hash,
        'frozen_protocol':frozen, 'source_metadata':source_meta, 'independent_review':review, 'measurements':pair,
        'source_words':len(source.split()), 'provider_calls':len(usage), 'providers':[{'provider':u['provider'],'model':u['model']} for u in usage],
        'elapsed_seconds':workflow['elapsed_seconds'], 'cost_usd':str(cost), 'completed_at':final_event['recorded_at'],
        'desklib_reduction_points':float(Decimal(str(before['ai_score'])) * 100 - Decimal(str(after['ai_score'])) * 100),
        'gate_passed':passed, 'thresholds':{str(n):max(after['ai_score'], pair['output']['vanguard']['measurement']['ai_score']) < n/100 for n in (30,10,2)},
        'vanguard_worsened':pair['output']['vanguard']['measurement']['ai_score'] > pair['original']['vanguard']['measurement']['ai_score']}

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


def phase_c_jobs(run, source, claims):
    folder = run / 'phase-c'
    paths = sorted((folder / 'jobs').glob('*.json'))
    if not (folder / 'protocol.json').exists():
        if paths:
            raise ValueError('Phase C jobs exist without activation')
        return []
    protocol = read(folder / 'protocol.json')
    approval = read(folder / 'approval.json')
    plan = read(folder / 'plan-draft.json')
    if (protocol.get('status') != 'activated' or protocol.get('phase') != 'C'
        or protocol.get('approval') != approval or approval.get('authorized') is not True
        or approval.get('phase') != 'C' or approval.get('max_new_calls') != 6
        or approval.get('max_new_distinct') != 151 or approval.get('global_budget_usd') != 1.5
        or approval.get('max_parent_score') != .35 or approval.get('plan_sha256') != sha(json.dumps(plan, sort_keys=True))
        or any(protocol.get(key) != value for key, value in plan.items() if key != 'status')
        or plan.get('source_sha256') != sha(source) or len(paths) > 151):
        raise ValueError('Phase C activation differs from its frozen plan or source')
    status = read(folder / 'status.json')
    if status.get('phase') != 'C':
        raise ValueError('Phase C status identity differs')
    requests = read(run / 'ledger.json')['requests']
    if sum(key.startswith('phase-c-') for key in requests) > 6:
        raise ValueError('Phase C exceeded its frozen provider request limit')
    if not paths:
        return []
    def provider_result(stage, provider):
        request_id = f'phase-c-{stage}-{provider}'
        request = read(run / 'rounds' / (request_id + '.request.json'))
        receipt = read(run / 'rounds' / (request_id + '.response.json'))
        who = {'claude':'anthropic', 'openai':'openai', 'grok':'xai'}[provider]
        expected_model = {'anthropic':'claude-sonnet-5-5','openai':'gpt-6.1-sol','xai':'grok-4.7'}[who]
        prompt = json.loads(request['prompt'])
        body = receipt['body']
        if (request.get('provider') != who or request.get('model') != expected_model
            or prompt.get('original') != source or prompt.get('claims') != claims
            or receipt.get('http_status') != 200
            or (who == 'anthropic' and body.get('stop_reason') != 'end_turn')
            or (who != 'anthropic' and (body.get('status') != 'completed' or body.get('incomplete_details')))):
            raise ValueError('Phase C provider receipt does not match its source-bound completed request')
        text = ''.join(x.get('text','') for x in body.get('content',[]) if x.get('type') == 'text') if who == 'anthropic' else ''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type') == 'output_text')
        output = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()))
        if requests.get(request_id, {}).get('fingerprint') != sha(json.dumps(request, sort_keys=True)):
            raise ValueError('Phase C request differs from the cost-ledger fingerprint')
        return output, prompt
    initial = read(folder / 'jobs/c00-draft.json')
    first, _ = provider_result('init', 'claude')
    second, second_prompt = provider_result('init', 'openai')
    final, final_prompt = provider_result('init', 'grok')
    expected_ids = {c['id'] for c in claims}
    faithful = final.get('faithful') is True and not final.get('issues') and len(final.get('checked_claim_ids',[])) == 32 and set(final['checked_claim_ids']) == expected_ids
    if (initial.get('kind') != 'fresh_three_provider_full_rewrite' or initial.get('parent_id') != 'source-original'
        or initial.get('parent_sha256') != sha(source) or initial.get('provider_review_faithful') != faithful
        or second_prompt.get('current_draft') != first.get('text') or final_prompt.get('current_draft') != second.get('text')
        or final != read(folder / 'initializer-review.json') or initial['text'] != final.get('text','').strip()):
        raise ValueError('Phase C fresh draft lineage differs from completed initializer evidence')
    jobs = [read(path) for path in paths]
    if any(j.get('phase') != 'C' for j in jobs):
        raise ValueError('Phase C candidate phase identity differs')
    descendants = [j for j in jobs if j['id'] != initial['id']]
    if descendants:
        admission = read(folder / 'admission-result.json')
        pair = load_pair(run, initial['sha256'])
        reviews = [(p, read(p)) for p in sorted((run / 'reviews').glob('*.json'))]
        if (admission.get('admitted') is not True or pair is None
            or max(pair[d]['measurement']['ai_score'] for d,_ in DETECTORS) > .35
            or len(approvals(reviews, initial['sha256'], sha(source), expected_ids)) < 2):
            raise ValueError('Phase C descendants lack an eligible competitive reviewed parent')
        bank = read(folder / 'bank.json')
        bank_review, bank_prompt = provider_result('bank', 'grok')
        if (bank.get('parent') != initial or bank.get('source_sha256') != sha(source)
            or bank_review != read(folder / 'bank-review.json') or bank_prompt.get('current') != initial['text']
            or bank_review.get('baseline_faithful') is not True or bank_review.get('baseline_issues')
            or len(bank_review.get('checked_claim_ids',[])) != 32 or set(bank_review['checked_claim_ids']) != expected_ids):
            raise ValueError('Phase C descendant bank is not bound to its reviewed parent')
        submitted = {p['id']:p for p in bank_prompt['patches']}
        approved = {p['id'] for p in bank_review['patches'] if p.get('faithful') is True and not p.get('issues')}
        patches = {p['id']:p for p in bank['patches']}
        if any(p not in approved or item != submitted.get(p) for p,item in patches.items()):
            raise ValueError('Phase C bank patches differ from provider-approved exact spans')
        for job in descendants:
            if job.get('parent_id') != initial['id'] or job.get('parent_sha256') != initial['sha256']:
                raise ValueError('Phase C descendant parent identity differs')
            ids = job.get('patch_ids',[])
            if not ids or len(ids) != len(set(ids)) or any(i not in patches for i in ids):
                raise ValueError('Phase C descendant patch identities differ')
            chosen = sorted((patches[i] for i in ids), key=lambda p:p['start'])
            if any(a['end'] > b['start'] for a,b in zip(chosen,chosen[1:])):
                raise ValueError('Phase C descendant spans overlap')
            text = initial['text']
            for patch in reversed(chosen):
                if text[patch['start']:patch['end']] != patch['find']:
                    raise ValueError('Phase C descendant exact span changed')
                text = text[:patch['start']] + patch['replace'] + text[patch['end']:]
            if text != job['text']:
                raise ValueError('Phase C descendant text differs from its patch combination')
    return jobs

PHASE_D_PLAN_SHA = '1c4581294ad31e3b6fcd8f15cbeee6e4482e233d1417ac3c854ef889cf2d9df8'


def phase_d_jobs(run, source, claims, previous):
    folder = run / 'phase-d'
    paths = sorted((folder / 'jobs').glob('*.json'))
    if not (folder / 'protocol.json').exists():
        if paths:
            raise ValueError('Phase D jobs exist without activation')
        return []
    plan, approval, protocol = (read(folder / name) for name in ('plan-draft.json','approval.json','protocol.json'))
    expected_approval = {'authorized':True,'phase':'D','plan_sha256':PHASE_D_PLAN_SHA,'max_banks':3,'max_new_calls':9,'max_new_distinct':450,'per_bank_max':150,'global_budget_usd':1.5}
    if (sha(json.dumps(plan,sort_keys=True)) != PHASE_D_PLAN_SHA
        or any(approval.get(k) != v for k,v in expected_approval.items())
        or protocol.get('status') != 'activated' or protocol.get('plan_sha256') != PHASE_D_PLAN_SHA
        or protocol.get('approval') != approval or protocol.get('source_sha256') != sha(source)
        or any(protocol.get(key) != value for key,value in plan.items() if key != 'status')):
        raise ValueError('Phase D activation differs from the fixed prospective plan or source')
    ledger = read(run / 'ledger.json')
    requests = ledger['requests']
    d_requests = [k for k in requests if k.startswith('phase-d-')]
    allowed = {f'phase-d-r{n:02d}-{p}' for n in range(1,4) for p in ('claude','openai','grok')}
    if (set(d_requests) - allowed or len(d_requests) > 9 or ledger.get('limit_usd') != 1.5
        or sum(Decimal(str(x.get('actual_usd',x['reserved_usd']))) for x in requests.values()) > Decimal('1.50')):
        raise ValueError('Phase D request identities or shared budget exceed the frozen limits')
    jobs = [read(path) for path in paths]
    if len(jobs) > 450 or len({j['sha256'] for j in jobs}) != len(jobs):
        raise ValueError('Phase D distinct-text count or uniqueness differs')
    excluded = {sha(source)} | {j['sha256'] for j in previous}
    if (run/'baseline.json').exists():
        excluded.add(read(run/'baseline.json')['sha256'])
    archived = ROOT/'static/research-ten-trials.json'
    if archived.exists():
        history = read(archived)
        excluded.update(row['sha256'] for row in [history['original'],history['baseline'],history['selected'],*history['trials'],*history['repairs']] if row.get('sha256'))
    if excluded & {j['sha256'] for j in jobs}:
        raise ValueError('Phase D includes a previously counted or reference text')
    known = {j['id']:j for j in previous + jobs}
    allowed_parents = {j['id']:j for j in previous if j.get('phase') != 'C'}
    allowed_parents.update({j['id']:j for j in jobs})
    ids = {c['id'] for c in claims}
    reviews = [(p,read(p)) for p in sorted((run/'reviews').glob('*.json'))]
    bank_numbers = {j.get('bank') for j in jobs}
    if any(type(n) is not int or not 1 <= n <= 3 for n in bank_numbers):
        raise ValueError('Phase D candidate bank number differs')
    for number in sorted(bank_numbers):
        bank_folder = folder/'banks'/f'd{number:02d}'
        bindings = read(bank_folder/'bindings.json')
        prefix = f'phase-d-r{number:02d}'
        expected_paths = {f'phase-d/banks/d{number:02d}/{name}.json' for name in ('context','review','bank')} | {f'rounds/{prefix}-grok.{kind}.json' for kind in ('request','response')}
        if set(bindings) != expected_paths or any(sha((run/path).read_text()) != digest for path,digest in bindings.items()):
            raise ValueError('Phase D frozen context/bank/provider evidence differs')
        context = read(bank_folder/'context.json'); bank=read(bank_folder/'bank.json'); parent=bank['parent']
        if (parent.get('id') not in allowed_parents or allowed_parents[parent['id']] != parent
            or sha(parent['text']) != parent.get('sha256') or parent.get('source_sha256') != sha(source)
            or context.get('parent') != parent or context.get('bank') != number
            or context.get('source_sha256') != sha(source) or bank.get('source_sha256') != sha(source)
            or (parent.get('phase') == 'D' and parent.get('bank',number) >= number)
            or (number == 1 and (parent['id'] != plan['initial_parent_id'] or parent['sha256'] != plan['initial_parent_sha256']))):
            raise ValueError('Phase D parent lineage differs from its frozen context')
        pair = load_pair(run,parent['sha256'])
        parent_reviews = approvals(reviews,parent['sha256'],sha(source),ids)
        current_reviewers = {r['review']['reviewer'] for r in parent_reviews}
        if (pair is None or context.get('parent_exact_scores') != [pair[d]['measurement']['ai_score'] for d,_ in DETECTORS]
            or len(set(context.get('parent_source_reviewers',[]))) < 2
            or not set(context['parent_source_reviewers']).issubset(current_reviewers)):
            raise ValueError('Phase D parent lacks matching paired measurements and two full source approvals')
        outputs={}; prompts={}; provider_events=[]
        for name,who,model in [('claude','anthropic','claude-sonnet-5-5'),('openai','openai','gpt-6.1-sol'),('grok','xai','grok-4.7')]:
            request_id=prefix+'-'+name
            request=read(run/'rounds'/(request_id+'.request.json'))
            receipt=read(run/'rounds'/(request_id+'.response.json')); body=receipt['body']
            prompt=json.loads(request['prompt']); entry=requests.get(request_id,{})
            if (request.get('provider') != who or request.get('model') != model
                or prompt.get('source') != source or prompt.get('claims') != claims or prompt.get('current') != parent['text']
                or entry.get('fingerprint') != sha(json.dumps(request,sort_keys=True))
                or receipt.get('http_status') != 200
                or (who == 'anthropic' and body.get('stop_reason') != 'end_turn')
                or (who != 'anthropic' and (body.get('status') != 'completed' or body.get('incomplete_details')))):
                raise ValueError('Phase D provider request/response does not match its completed source-bound call')
            text=''.join(x.get('text','') for x in body.get('content',[]) if x.get('type') == 'text') if who == 'anthropic' else ''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type') == 'output_text')
            outputs[name]=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip()));prompts[name]=prompt
            provider_events.append(datetime.fromisoformat(entry['started_at']))
        context_time=datetime.fromisoformat(context['at'])
        if context_time > min(provider_events) or prompts['openai'].get('proposed') != outputs['claude']:
            raise ValueError('Phase D frozen context or proposal chain differs')
        from scripts.research.recovery import valid_patch, numbers, clean
        refined=[]
        for item in outputs['openai'].get('patches',[]):
            if not isinstance(item.get('id'),str) or any(p['id'] == item['id'] for p in refined):
                continue
            patch=valid_patch(parent['text'],item)
            if patch:refined.append(patch)
        if len(refined) > 24 or prompts['grok'].get('patches') != refined:
            raise ValueError('Phase D reviewer did not receive the exact validated refined patches')
        review=outputs['grok'];rows=review.get('patches',[])
        checked={row['id']:row for row in rows}
        if (review != read(bank_folder/'review.json') or review.get('baseline_faithful') is not True
            or review.get('baseline_issues') or len(review.get('checked_claim_ids',[])) != 32 or set(review['checked_claim_ids']) != ids
            or len(checked) != len(rows) or set(checked) != {p['id'] for p in refined}):
            raise ValueError('Phase D full-source or exact patch approval differs from the raw response')
        approved=[p for p in refined if checked[p['id']].get('faithful') is True and not checked[p['id']].get('issues')]
        if approved != bank.get('patches'):
            raise ValueError('Phase D approved bank differs from its raw provider review')
        patches={p['id']:p for p in approved}
        own=[j for j in jobs if j['bank'] == number]
        if len(own) > 150:
            raise ValueError('Phase D per-bank text cap exceeded')
        deltas={}
        if any('-c' in j['id'] for j in own):
            from scripts.research.phase_b import logit
            base=[logit(pair[d]['measurement']['ai_score']) for d,_ in DETECTORS]
            for patch in approved:
                single=parent['text'][:patch['start']]+patch['replace']+parent['text'][patch['end']:]
                measured=load_pair(run,sha(single))
                if measured is None:
                    raise ValueError('Phase D combination lacks exact paired single-patch ranking inputs')
                deltas[patch['id']]=[logit(measured[d]['measurement']['ai_score'])-original for (d,_),original in zip(DETECTORS,base)]
        for job in own:
            patch_ids=job.get('patch_ids',[])
            if (job.get('phase') != 'D' or job.get('source_sha256') != sha(source)
                or re.fullmatch(f'd{number:02d}-[sc][0-9]{{3}}',job['id']) is None
                or job.get('parent_id') != parent['id'] or job.get('parent_sha256') != parent['sha256']
                or not patch_ids or len(patch_ids) != len(set(patch_ids)) or any(i not in patches for i in patch_ids)):
                raise ValueError('Phase D candidate identity or approved patch IDs differ')
            chosen=sorted((patches[i] for i in patch_ids),key=lambda p:p['start'])
            if any(a['end'] > b['start'] for a,b in zip(chosen,chosen[1:])):
                raise ValueError('Phase D candidate combines overlapping patches')
            text=parent['text']
            for patch in reversed(chosen):
                if text[patch['start']:patch['end']] != patch['find']:
                    raise ValueError('Phase D candidate exact span changed')
                text=text[:patch['start']]+patch['replace']+text[patch['end']:]
            if (text != job['text'] or sha(text) != job['sha256'] or not clean(text)
                or numbers(text) != numbers(source) or text.split('\n')[0] != source.split('\n')[0]
                or text.count(source.split('\n')[0]) != 1):
                raise ValueError('Phase D candidate text/hash/protected content differs from reconstruction')
            if '-s' in job['id']:
                if len(patch_ids) != 1 or 'ranking_only_predicted_logits' in job:
                    raise ValueError('Phase D single-patch identity differs')
            elif '-c' in job['id']:
                if not 2 <= len(patch_ids) <= 6 or job.get('prediction_is_not_a_measurement') is not True:
                    raise ValueError('Phase D combination lacks rank-only prediction labeling')
                expected=list(base)
                for patch in approved:
                    if patch['id'] in patch_ids:
                        expected=[value+delta for value,delta in zip(expected,deltas[patch['id']])]
                predicted=job.get('ranking_only_predicted_logits',[])
                if len(predicted) != 2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v-e)>1e-12 for v,e in zip(predicted,expected)):
                    raise ValueError('Phase D rank-only predictions differ from the exact single-patch inputs')
            else:
                raise ValueError('Phase D candidate has unknown single/combination identity')
        singles=read(bank_folder/'singles.json')
        if singles.get('bank') != number or len(singles.get('singles',[])) != len(approved):
            raise ValueError('Phase D single-patch manifest differs')
        for row,patch in zip(singles['singles'],approved):
            single=parent['text'][:patch['start']]+patch['replace']+parent['text'][patch['end']:]
            if row.get('patch_id') != patch['id'] or row.get('sha256') != sha(single):
                raise ValueError('Phase D single-patch receipt hash differs from the approved patch')
            if row.get('job_id'):
                if row['job_id'] not in known or known[row['job_id']]['sha256'] != sha(single):
                    raise ValueError('Phase D queued single-patch identity differs')
            elif load_pair(run,sha(single)) is None:
                raise ValueError('Phase D reused single patch lacks exact paired measurements')
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
    phase_c = phase_c_jobs(run, source, claims)
    phase_d = phase_d_jobs(run, source, claims, phase_a + phase_b + phase_c)
    if phase_b and ({j['sha256'] for j in phase_a} & {j['sha256'] for j in phase_b} or len({j['sha256'] for j in phase_a}) != 1000):
        raise ValueError('Phase B requires 1000 distinct phase A texts and no duplicate text across phases')
    prior_hashes = {j['sha256'] for j in phase_a + phase_b}
    if prior_hashes & {j['sha256'] for j in phase_c}:
        raise ValueError('Phase C includes a previously counted candidate text')
    if {j['sha256'] for j in phase_a + phase_b + phase_c} & {j['sha256'] for j in phase_d}:
        raise ValueError('Phase D includes a previously counted candidate text')
    jobs = phase_a + phase_b + phase_c + phase_d
    phases = {job['id']: phase for phase, items in [('A', phase_a), ('B', phase_b), ('C', phase_c), ('D', phase_d)] for job in items}
    baseline = read(run / 'baseline.json')
    by_hash, by_id = {}, {}
    original_node = {'id':'source-original','text':source,'sha256':source_hash,'source_sha256':source_hash}
    for item in [original_node, baseline] + jobs:
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
        while item['id'] not in (baseline['id'], original_node['id']):
            if item['id'] in seen:
                raise ValueError('Cyclic candidate lineage')
            seen.add(item['id']); chain.append(item['id'])
            parent = by_id.get(item.get('parent_id'))
            if not parent or item.get('parent_sha256') != parent['sha256']:
                raise ValueError('Candidate parent hash mismatch')
            item = parent
        return [item['id']] + list(reversed(chain))
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
        'phase_counts': [{'phase': phase, 'unique': len({j['sha256'] for j in items} - {source_hash, baseline['sha256']}), 'paired': sum(item['phase'] == phase for item in paired), 'reviewed': sum(item['phase'] == phase for item in eligible), 'new_provider_requests': sum(not k.startswith(('phase-c-','phase-d-')) for k in requests) if phase == 'A' else sum(k.startswith('phase-'+phase.lower()+'-') for k in requests) if phase in ('C','D') else 0, 'verified_thresholds': {str(n): any(item['phase'] == phase and item['maximum'] < n/100 for item in eligible) for n in (30,10,2)}} for phase, items in [('A', phase_a), ('B', phase_b), ('C', phase_c), ('D', phase_d)] if items or (phase in ('C','D') and any(k.startswith('phase-'+phase.lower()+'-') for k in requests))],
        'unique_candidates': len({j['sha256'] for j in jobs} - {source_hash, baseline['sha256']}), 'paired_candidates': len(paired), 'reviewed_candidates': len(eligible),
        'thresholds': {str(n): any(item['maximum'] < n / 100 for item in eligible) for n in (30, 10, 2)},
        'provider_requests': len(requests), 'completed_provider_calls': len(completed), 'unknown_cost_requests': len(requests) - len(completed),
        'completed_patch_banks': sum(x.get('status') == 'generated' for x in rounds) + int((run / 'phase-c/bank-complete.json').exists()) + len({j['bank'] for j in phase_d}), 'estimated_or_reserved_usd': str(estimate),
        'cost_limit_usd': ledger['limit_usd'], 'protocol': protocol, 'production_commit': production_commit,
        'end_to_end': end_to_end(run, source), 'holdout': holdout_data(run)}


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


def holdout_section(item):
    if item is None:
        return ''
    original = {d:item['measurements']['original'][d]['measurement']['ai_score'] for d,_ in DETECTORS}
    output = {d:item['measurements']['output'][d]['measurement']['ai_score'] for d,_ in DETECTORS}
    rows = ''.join(f'<tr><td>{d.title()}{" · used for selection" if d == "desklib" else " · held out until final selection"}</td><td class="nowrap">{exact_score(original[d])}</td><td class="nowrap">{exact_score(output[d])}</td><td>{"Lower" if output[d] < original[d] else "Higher"} by {abs(output[d]-original[d])*100:.2f} points</td></tr>' for d,_ in DETECTORS)
    gate_label = 'Passed' if item['gate_passed'] else 'Not passed'
    source_review = item['independent_review']
    claims = ''.join(f'<li><strong>{esc(row["id"])}</strong> {esc(row["reason"])}</li>' for row in source_review['claim_results'])
    providers = ' · '.join(esc(p['model']) for p in item['providers'])
    target_labels = ''.join(f'<span class="pill{("" if passed else " pending")}">Both below {target}: {"verified" if passed else "not reached"}</span>' for target,passed in item['thresholds'].items())
    return f'''<section class="card" style="margin-top:25px"><span class="label">Separate unseen business-source test · completed {esc(item['completed_at'])}</span><h2>A stronger test exposed a limitation.</h2><p>The strategy was frozen before this new {item['source_words']}-word business note was authored. All three writing APIs completed an actual workspace run. Desklib guided candidate selection; Vanguard was withheld until the final text had been chosen.</p><div class="notice"><strong>Frozen performance gate: {gate_label.lower()}.</strong> Desklib fell from {original['desklib']*100:.2f} to {output['desklib']*100:.2f}, a {item['desklib_reduction_points']:.2f}-point reduction. The predeclared requirement was an output below 30 plus a reduction of at least 10 points and a complete source-review pass. The held-out Vanguard score {"worsened" if item['vanguard_worsened'] else "changed"} from {original['vanguard']*100:.2f} to {output['vanguard']*100:.2f}.</div><div class="table-wrap"><table><thead><tr><th>Detector</th><th>Original / 100, exact</th><th>Final / 100, exact</th><th>Change</th></tr></thead><tbody>{rows}</tbody></table></div><div class="targets">{target_labels}</div><p><strong>Source fidelity passed; the performance gate did not.</strong> An independent agent inventory covered 48 source claims before the output was viewed. Its score-blind final review found all 48 preserved, with no unsupported additions or whole-document quality issues. This does not certify human authorship.</p><p><strong>The experimental mode remains disabled.</strong> This was a workspace validation run, not a document generated through the live website. It is separate from the adaptive garden-note study, and neither its source nor its output is counted among those research variants.</p><p class="fine">{item['provider_calls']} completed provider calls · {esc(item['elapsed_seconds'])} seconds · ${esc(item['cost_usd'])} estimated API cost, not an invoice.<br>{providers}<br>Frozen strategy SHA-256: <code>{esc(item['frozen_protocol']['strategy_sha256'])}</code></p><details><summary>Holdout protocol and independent review</summary><div><p class="fine">Freeze: {esc(item['frozen_protocol']['created_at'])}<br>New source authored: {esc(item['source_metadata']['authored_at'])}<br>Independent reviewer: <code>{esc(source_review['reviewer'])}</code></p><p class="fine">{esc(source_review['whole_source_review']['assessment'])}</p><ol class="checklist">{claims}</ol></div></details></section><section><div class="section-heading"><div><span class="label">Separate holdout · exact full text</span><h2>The unseen source and final output.</h2></div><p>Preserved without subsequent edits. Both detector receipts and the 48-claim review bind these exact hashes.</p></div><div class="compare">{document_panel('Original business note','holdout-original',item['source'],item['source_sha256'],original,'New source · authored after strategy freeze')}{document_panel('Prototype final output','holdout-output',item['output'],item['output_sha256'],output,'Source review passed · performance gate failed')}</div></section>'''


def render(data):
    logo = base64.b64encode((ROOT / 'static/txtzi-logo.svg').read_bytes()).decode()
    dark_logo = base64.b64encode((ROOT / 'static/txtzi-logo-dark.svg').read_bytes()).decode()
    brand = f'<img class="logo-screen" src="data:image/svg+xml;base64,{dark_logo}" width="180" height="56" alt="txtzi"><img class="logo-print" src="data:image/svg+xml;base64,{logo}" width="180" height="56" alt="txtzi">'
    selected = data['selected']; job = selected['job']; scores = selected['scores']
    original_scores = {d: data['original_receipts'][d]['measurement']['ai_score'] for d, _ in DETECTORS}
    thresholds = ''.join(f'<span class="pill{("" if passed else " pending")}">Both below {target}: {"verified" if passed else "not reached"}</span>' for target, passed in data['thresholds'].items())
    exact_rows = ''.join(f'<tr><td>{d.title()}</td><td class="nowrap">{exact_score(original_scores[d])}</td><td class="nowrap">{exact_score(scores[d])}</td></tr>' for d, _ in DETECTORS)
    phase_rows = ''.join(f'<tr><td>Phase {row["phase"]}</td><td>{row["unique"]:,}</td><td>{row["paired"]:,}</td><td>{row["reviewed"]:,}</td><td>{row["new_provider_requests"]}</td><td>{'; '.join('below '+n+': '+('verified' if ok else 'not reached') for n,ok in row['verified_thresholds'].items())}</td></tr>' for row in data['phase_counts'])
    phase_table = f'<div class="table-wrap"><table><thead><tr><th>Study phase</th><th>Distinct candidates</th><th>Paired measurements</th><th>Two approvals</th><th>New provider requests</th><th>Both-detector thresholds</th></tr></thead><tbody>{phase_rows}</tbody></table></div>'
    phase_note = 'Phase B reuses frozen, reviewed patch banks from phase A with no new writing API calls. Predicted ranks only choose combinations to test; every displayed result comes from new exact-text detector inference.' if any(row['phase'] == 'B' for row in data['phase_counts']) else 'Phase B is not included in this checkpoint.'
    if any(row['phase'] == 'C' for row in data['phase_counts']):
        phase_note += ' Phase C separately starts a fresh full draft from the original with three new provider calls; a descendant patch bank is permitted only after competitive paired scores and two complete source reviews.'
    if any(row['phase'] == 'D' for row in data['phase_counts']):
        phase_note += ' Phase D separately adds at most three reviewed patch banks and 450 new distinct texts under the same shared API cap. Each bank starts from an exact-measured parent with two complete approvals. Exact single-patch measurements rank new combinations; predictions never become reported measurements.'
    holdout = holdout_section(data.get('holdout'))
    holdout_notice = '<div class="notice"><strong>Separate unseen-source check: performance gate failed.</strong> The source review passed, but the frozen business-note test missed its required improvement and worsened on the detector withheld from selection. The experimental mode remains disabled. Read the complete result below.</div>' if data.get('holdout') and not data['holdout']['gate_passed'] else ''
    header_scope = 'Adaptive research plus a separate unseen-source check' if data.get('holdout') else 'One English research source'
    audit_details = ''.join(f'<div class="audit-note"><strong>Independent review {i}</strong><p><code>{esc(a["review"]["reviewer"])}</code></p><p>{esc(a["review"]["whole_source_review"].get("assessment", "All whole-source checks passed."))}</p><p>32 / 32 source claims preserved · reviewed blind to scores · no reported issues</p></div>' for i, a in enumerate(selected['approvals'], 1))
    claims = ''.join(f'<li><strong>{esc(row["id"])}</strong> {esc(row["reason"])}</li>' for row in selected['approvals'][0]['review']['claim_results'])
    pin_rows = ''.join(f'<tr><td>{d.title()}</td><td>{esc(data["protocol"]["detectors"][d]["model"])}</td><td><code>{rev}</code></td></tr>' for d, rev in DETECTORS)
    e2e_rows = ''.join(f'<tr><td>{esc(r["id"])}</td><td>{exact_score(r["score"])}</td><td>{r["provider_calls"]}</td><td>{r["attempts"]}</td><td>{esc(r["elapsed_seconds"])} s</td><td>{"Original retained after an incomplete meaning inventory" if r["original_retained"] else "Completed; target performance not reached"}</td></tr>' for r in data['end_to_end'])
    e2e = f'<div class="table-wrap"><table><thead><tr><th>Prototype run</th><th>Final Desklib / 100</th><th>Provider calls</th><th>Measured texts</th><th>Duration</th><th>Outcome</th></tr></thead><tbody>{e2e_rows}</tbody></table></div>' if data['end_to_end'] else '<p>No completed end-to-end prototype records were available at this checkpoint.</p>'
    commit = esc(data['production_commit'] or 'Not supplied for this checkpoint')
    embedded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>txtzi — Private test comparison</title><style>{CSS}</style></head><body><header><div class="brand">{brand}</div><div class="eyebrow">Private research checkpoint · {header_scope}</div><h1>Better wording.<br>Measured with context.</h1><p>Your original text and the strongest fully reviewed draft in the preserved recovery study. Every displayed research result is tied to the exact text, two detector receipts and independent source reviews. A separate frozen business-source test is included when available.</p><div class="meta">Prepared {esc(data['checkpoint_at'])} · No external resources or live API calls are needed to read this file.</div></header><main><section class="summary"><div class="card"><span class="label">Best verified research draft · phase {esc(selected['phase'])} · {esc(job['id'])}</span><div class="metric-pair"><div class="metric"><strong>{scores['desklib'] * 100:.2f}</strong><small>Desklib / 100</small></div><div class="metric"><strong>{scores['vanguard'] * 100:.2f}</strong><small>Vanguard / 100</small></div></div><span class="pill">Two independent complete source approvals</span><p class="fine">Cards round to two decimals. Exact stored values appear below. These are uncalibrated model estimates, not percentages of AI-written words or proof of authorship.</p></div><div class="card"><span class="label">Your requested thresholds</span><h2>Both detectors must qualify.</h2><div class="targets">{thresholds}</div><p class="fine">A target is marked verified only when the same full text scores strictly below it on both fixed models and has two distinct, complete source approvals. Lower-scoring unaudited candidates are never promoted here.</p></div></section>{holdout_notice}<div class="notice"><strong>This is a research result, not the current app output.</strong> Both detectors were used repeatedly to choose changes to this one synthetic source. There is no held-out detector or independent-document success rate. This does not establish reliable bypass of other checkers or removal of statistical watermarks.</div><section class="counts" aria-label="Current study counts"><div><strong>{data['unique_candidates']:,}</strong><span>Distinct generated candidate texts</span></div><div><strong>{data['paired_candidates']:,}</strong><span>Candidates scored by both models</span></div><div><strong>{data['reviewed_candidates']:,}</strong><span>Paired candidates with two full approvals</span></div><div><strong>{data['completed_patch_banks']:,}</strong><span>Completed shared three-provider patch banks</span></div></section><p class="fine">Counts cover the rebuilt study only. Original and starting-reference texts are excluded. A patch bank combines Claude, OpenAI and Grok work into many distinct variants; these are not {data['unique_candidates']:,} independent three-model end-to-end rewrites. Earlier lost runs are not counted.</p>{phase_table}<p class="fine">{phase_note}</p>{holdout}<section><div class="section-heading"><div><span class="label">Adaptive garden-note research · full text comparison</span><h2>Your source. The reviewed result.</h2></div><p>Copy or download either exact text. All paragraphs and the title are included; no text is shortened for this comparison.</p></div><div class="compare">{document_panel('Original source','original',data['source'],data['source_sha256'],original_scores,'Before · immutable synthetic source')}{document_panel('Selected research draft','selected',job['text'],job['sha256'],scores,'After · two complete independent reviews')}</div><div class="status" id="action-status" role="status" aria-live="polite"></div></section><section class="two-column"><div class="card"><h3>Exact measurements out of 100</h3><div class="table-wrap"><table><thead><tr><th>Detector</th><th>Original</th><th>Selected</th></tr></thead><tbody>{exact_rows}</tbody></table></div><p class="fine">{esc(data['original_note'])}</p><p class="fine">Each selected score covers the full candidate text and matches its SHA-256. Selection minimizes the larger of the two scores among candidates that pass both independent reviews.</p></div><div class="card"><h3>Calls, cost and lineage</h3><p><strong>{data['provider_requests']}</strong> provider requests recorded; <strong>{data['completed_provider_calls']}</strong> have returned usage and estimated costs. <strong>{data['unknown_cost_requests']}</strong> retain a conservative reservation.</p><p><strong>${esc(data['estimated_or_reserved_usd'])}</strong> estimated or reserved research API cost, within a <strong>${esc(data['cost_limit_usd'])}</strong> shared API cap.</p><p class="fine">This is not an invoice. Hosting and separate end-to-end validation costs are excluded. Shared patch banks and unresolved charges remain counted.</p><p class="fine"><strong>Selected lineage:</strong><br>{esc(' → '.join(selected['lineage']))}</p></div></section><section class="card" style="margin-top:25px"><span class="label">Production readiness</span><h2>The app and the experiment remain separate.</h2><p>The published application remains on its <strong>meaning-first-v2</strong> workflow. The bounded prototype was tested independently from the full original; it did not achieve the requested performance target and has not replaced that default.</p>{e2e}<p class="fine">The bounded prototype’s tiny score change is not equivalent to this adaptive study’s best result. Its successful complete run uses all three writing providers; the earlier stopped run did not. Only Desklib guides that prototype, so a second-detector target is not established by these app-style runs.</p><p class="fine"><strong>Production commit recorded by the operator:</strong> <code>{commit}</code></p></section><details><summary>Source-review evidence · all 32 claims</summary><div>{audit_details}<ol class="checklist">{claims}</ol><p class="fine">Reviewer identities are recorded agent IDs. “Independent” here means separate reviews of the full source and candidate, blind to the candidate scores; it does not mean external human certification.</p></div></details><details><summary>Detector versions and reproducibility</summary><div class="table-wrap"><table><thead><tr><th>Detector</th><th>Model</th><th>Pinned revision</th></tr></thead><tbody>{pin_rows}</tbody></table><p class="fine">Selected-candidate settings: Desklib uses 512-token windows with 64-token overlap, bfloat16 matrix storage and float32 compute. Vanguard uses float32, SDPA, reference compilation disabled, no truncation and a maximum 8,192 tokens. Exact hashes bind the source, candidate and score receipts. This file includes the selected receipts and reviews as inert JSON for inspection.</p></div></details><footer class="footer"><span>txtzi · Private owner report · Generated from preserved evidence at the stated checkpoint.<br>No authorship guarantee, universal detector-pass claim or watermark-removal certification.</span><button class="print" id="print-report">Print / Save as PDF</button></footer></main><script type="application/json" id="report-evidence">{embedded}</script><script>{JS}</script></body></html>'''


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
