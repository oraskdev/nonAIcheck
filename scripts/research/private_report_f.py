"""Read-only validation of the separately authorized cached-proposal Phase F.

No provider calls, runner admission, artifact writes, or embedded research corpus.
Only exact detector receipts are measurements; the caller owns final source-review
promotion. Incomplete paid attempts remain visible without creating candidate tests.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PLAN_SHA = '030af446cfe88aafc97e040e319b73040dd31709e16f2a10d3e8b3890a54c9bd'
SHARED = {'scripts/research/recovery.py', 'scripts/research/phase_b.py',
          'scripts/research/phase_d.py', 'scripts/research/score.py'}
RUNNERS = {'scripts/research/phase_f.py', 'scripts/research/score_phase_f.py'}
MODELS = {'anthropic': 'claude-sonnet-5-5', 'openai': 'gpt-6.1-sol', 'xai': 'grok-4.7'}


def _read(path):
    return json.loads(Path(path).read_text())


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError('Phase F ' + message)


def _time(value):
    time = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _require(time.tzinfo is not None, 'timestamp lacks timezone')
    return time


def _bound_files(base, mapping, expected):
    _require(isinstance(mapping, dict) and set(mapping) == expected, 'frozen file set differs')
    for relative, digest in mapping.items():
        _require(_sha((base / relative).read_text()) == digest, 'frozen file changed: ' + relative)


def _response(receipt, provider):
    body = receipt.get('body', {})
    _require(receipt.get('http_status') == 200, 'provider response failed')
    if provider == 'anthropic':
        _require(body.get('stop_reason') == 'end_turn', 'cached Claude response is incomplete')
        text = ''.join(p.get('text', '') for p in body.get('content', []) if p.get('type') == 'text')
    else:
        _require(body.get('status') == 'completed' and not body.get('incomplete_details'), 'provider response is incomplete')
        text = ''.join(p.get('text', '') for item in body.get('output', [])
                       for p in item.get('content', []) if p.get('type') == 'output_text')
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()))


def _request(request, provider, source, claims, parent):
    _require(request.get('provider') == provider and request.get('model') == MODELS[provider]
             and request.get('max_output_tokens') == 4500, 'provider/model/output-cap binding differs')
    prompt = json.loads(request['prompt'])
    _require(prompt.get('source') == source and prompt.get('claims') == claims
             and prompt.get('current') == parent['text'], 'request source/claims/parent binding differs')
    return prompt


def _decisions(parent, proposals, answer, valid_patch):
    rows = answer.get('decisions', [])
    _require(isinstance(rows, list) and all(isinstance(x, dict) for x in rows), 'decision schema differs')
    decisions = {x.get('id'): x for x in rows}
    _require(len(rows) == len(proposals) and len(decisions) == len(rows)
             and set(decisions) == {x['id'] for x in proposals}, 'exhaustive decision coverage differs')
    retained = []
    for original in proposals:
        row = decisions[original['id']]
        action = row.get('action')
        _require(action in ('accept', 'repair', 'reject') and isinstance(row.get('reason'), str)
                 and row['reason'].strip(), 'decision lacks an explicit valid action/reason')
        _require(row.get('find') in (None, original['find']), 'decision changed the fixed find span')
        if action == 'reject':
            continue
        _require(action != 'accept' or row.get('replace') in (None, original['replace']), 'accepted patch was silently changed')
        replacement = row.get('replace') if action == 'repair' else original['replace']
        patch = valid_patch(parent['text'], {'id': original['id'], 'find': original['find'], 'replace': replacement})
        _require(patch is not None, 'retained patch violates exact span/protected-value guards')
        retained.append(patch)
    return retained


def _review(claims, retained, review):
    rows = review.get('patches', [])
    _require(isinstance(rows, list) and all(isinstance(x, dict) for x in rows), 'Grok patch schema differs')
    for row in rows:
        issues = row.get('issues')
        _require(isinstance(row.get('faithful'), bool) and isinstance(issues, list)
                 and all(isinstance(issue, str) and issue.strip() for issue in issues)
                 and (row['faithful'] is True or bool(issues)), 'Grok verdict requires a boolean and explicit rejection issues')
    by_id = {x.get('id'): x for x in rows}
    ids = {x['id'] for x in claims}
    _require(review.get('baseline_faithful') is True and not review.get('baseline_issues')
             and len(review.get('checked_claim_ids', [])) == 32 and set(review['checked_claim_ids']) == ids
             and len(rows) == len(by_id) and set(by_id) == {x['id'] for x in retained},
             'Grok whole-source/patch coverage failed')
    return [p for p in retained if by_id[p['id']].get('faithful') is True and not by_id[p['id']].get('issues')]


def _apply(text, patches):
    patches = sorted(patches, key=lambda p: p['start'])
    _require(not any(a['end'] > b['start'] for a, b in zip(patches, patches[1:])), 'candidate spans overlap')
    for patch in reversed(patches):
        _require(text[patch['start']:patch['end']] == patch['find'], 'candidate exact span changed')
        text = text[:patch['start']] + patch['replace'] + text[patch['end']:]
    return text


def _logit(value):
    value = max(1e-7, min(1 - 1e-7, value))
    return math.log(value / (1 - value))


def _actual_usage(entry, receipt, provider):
    usage = entry.get('usage', {})
    _require(entry.get('status') == 'response_saved' and isinstance(entry.get('actual_usd'), (int, float))
             and not isinstance(entry['actual_usd'], bool) and math.isfinite(entry['actual_usd'])
             and entry['actual_usd'] >= 0 and receipt.get('body', {}).get('usage') == usage
             and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')),
             'actual usage is not reconciled to its saved receipt')
    rate = 6 if provider == 'xai' else 10
    _require(abs(entry['actual_usd'] - (usage['input_tokens'] * 2 + usage['output_tokens'] * rate) / 1e6) <= 1e-12,
             'actual usage cost differs from the frozen rates')


def phase_f_data(run, source, claims, previous, *, code_root=None):
    """Return validated jobs and actual phase state; never create a missing artifact."""
    from scripts.research.private_report import approvals, load_pair, DETECTORS
    from scripts.research.recovery import valid_patch, numbers, clean
    run, code_root = Path(run), Path(code_root or ROOT)
    folder = run / 'phase-f'
    book = _read(run / 'ledger.json')
    requests = book['requests']
    names = [name for name in requests if name.startswith('phase-f-')]
    paths = sorted((folder / 'jobs').glob('*.json'))
    result = {'phase': 'F', 'jobs': [], 'state': 'absent', 'provider_requests': len(names),
              'new_provider_requests': len(names), 'completed_patch_banks': 0,
              'completed_provider_calls': 0, 'new_claude_calls': 0, 'maximum_new_distinct': 300,
              'cached_proposal_records': 0, 'unique_cached_proposals': 0, 'unique_generated': 0,
              'cached_origin_count': 0, 'cached_proposal_count': 0,
              'paired': 0, 'estimated_or_reserved_usd': '0', 'unknown_cost_requests': 0,
              'scope': 'One-source adaptive research; cached proposals are not generated or measured tests.',
              'limits': {'new_provider_calls': 2, 'new_claude_calls': 0, 'new_distinct_texts': 300,
                         'output_tokens_per_request': 4500, 'shared_global_api_usd': 1.5}}
    if not (folder / 'plan-draft.json').exists():
        _require(not names and not paths and not (folder / 'approval.json').exists()
                 and not (folder / 'protocol.json').exists(), 'execution artifacts exist without a prospective plan')
        return result
    plan = _read(folder / 'plan-draft.json')
    _require(_sha(json.dumps(plan, sort_keys=True)) == PLAN_SHA and plan.get('phase') == 'F'
             and plan.get('source_sha256') == _sha(source), 'fixed prospective plan/source changed')
    result.update(state='proposed', plan=plan, cached_proposal_records=26, unique_cached_proposals=23,
                  cached_origin_count=26, cached_proposal_count=23, scope=plan.get('scope', result['scope']))
    _bound_files(code_root, plan['frozen_shared_code_sha256'], SHARED)
    expected_e = {f'phase-e/banks/e{n:02d}/context.json' for n in (1, 2)} | {
        f'rounds/phase-e-r{n:02d}-{p}.{kind}.json' for n in (1, 2)
        for p in ('claude', 'openai') for kind in ('request', 'response')}
    _bound_files(run, plan['frozen_e_file_sha256'], expected_e)
    manifest_path = folder / 'cached-proposals.json'
    manifest = _read(manifest_path)
    _require(_sha(manifest_path.read_text()) == plan['cached_proposals_sha256']
             and manifest.get('frozen_e_file_sha256') == plan['frozen_e_file_sha256'], 'cached proposal manifest binding changed')
    parent = manifest['parent']
    previous_by_id = {j['id']: j for j in previous}
    _require(parent.get('id') == 'd03-s005' == plan['parent_id']
             and parent.get('sha256') == plan['parent_sha256'] == _sha(parent['text'])
             and parent.get('source_sha256') == manifest.get('source_sha256') == _sha(source)
             and previous_by_id.get(parent['id']) == parent, 'fixed parent/source/history binding differs')
    expected_ids = {f'G{i:02d}' for i in range(1, 33)}
    _require(len(claims) == 32 and {c['id'] for c in claims} == expected_ids, 'source claim inventory differs')
    reviews = [(p, _read(p)) for p in sorted((run / 'reviews').glob('*.json'))]
    pair = load_pair(run, parent['sha256'])
    parent_reviews = approvals(reviews, parent['sha256'], _sha(source), expected_ids)
    _require(pair is not None and max(pair[d]['measurement']['ai_score'] for d, _ in DETECTORS) < .10
             and len(parent_reviews) >= 2, 'fixed parent lacks exact below-10 measurements and two complete approvals')
    ejobs = [_read(p) for p in sorted((run / 'phase-e/jobs').glob('*.json'))]
    _require(len(ejobs) == 58 and len({j['sha256'] for j in ejobs}) == 58, 'completed E58 prerequisite differs')
    for job in ejobs:
        _require(job.get('phase') == 'E' and job.get('source_sha256') == _sha(source)
                 and job.get('sha256') == _sha(job['text']) and previous_by_id.get(job['id']) == job
                 and load_pair(run, job['sha256']) is not None, 'E prerequisite lacks bound exact paired texts')
    reconstructed = {}
    for n in (1, 2):
        _require(_read(run / f'phase-e/banks/e{n:02d}/context.json')['parent'] == parent, 'cached bank parent differs')
        outputs = {}
        for suffix, who in (('claude', 'anthropic'), ('openai', 'openai')):
            name = f'phase-e-r{n:02d}-{suffix}'
            request = _read(run / f'rounds/{name}.request.json')
            prompt = _request(request, who, source, claims, parent)
            outputs[suffix] = _response(_read(run / f'rounds/{name}.response.json'), who)
            if suffix == 'openai':
                _require(prompt.get('proposed') == outputs['claude'], 'cached proposal/refinement chain differs')
        cp, op = outputs['claude']['patches'], outputs['openai']['patches']
        _require(len({p['id'] for p in cp}) == len(cp) and len({p['id'] for p in op}) == len(op), 'cached proposal IDs repeat')
        returned = {p['id'] for p in op}
        for proposal in cp:
            if proposal['id'] in returned:
                continue
            patch = valid_patch(parent['text'], proposal)
            _require(patch is not None, 'cached omitted proposal violates unchanged guards')
            reconstructed.setdefault((patch['find'], patch['replace']), {'patch': patch, 'origins': []})['origins'].append(
                {'bank': n, 'original_proposal_id': proposal['id']})
    proposals = [{**v['patch'], 'id': f'f-p{i:03d}', 'claude_origins': v['origins']}
                 for i, v in enumerate(reconstructed.values(), 1)]
    _require(len(proposals) == 23 and sum(len(p['claude_origins']) for p in proposals) == 26
             and manifest.get('proposals') == proposals, 'cached 26-to-23 proposal reconstruction differs')
    prompt_path = folder / 'prospective-openai-prompt.json'
    prompt = _read(prompt_path)
    _require(_sha(prompt_path.read_text()) == plan['prospective_openai_prompt_sha256']
             and prompt.get('source') == source and prompt.get('current') == parent['text']
             and prompt.get('claims') == claims
             and prompt.get('proposals') == [{k: v for k, v in p.items() if k != 'claude_origins'} for p in proposals],
             'frozen exhaustive-review prompt differs')
    total = Decimal('0'); phase_cost = Decimal('0')
    for name, entry in requests.items():
        amount = Decimal(str(entry.get('actual_usd', entry['reserved_usd'])))
        _require(amount.is_finite() and amount >= 0, 'ledger contains an invalid cost')
        total += amount
        if name in names:
            phase_cost += amount
    _require(book.get('limit_usd') == 1.5 and total <= Decimal('1.50'), 'shared API budget exceeds frozen cap')
    _require(set(names).issubset({'phase-f-openai', 'phase-f-grok'}) and len(names) <= 2, 'new request identities exceed permitted providers/cap')
    result.update(estimated_or_reserved_usd=str(phase_cost), global_estimated_or_reserved_usd=str(total),
                  parent_id=parent['id'], parent_sha256=parent['sha256'],
                  unknown_cost_requests=sum('actual_usd' not in requests[name] for name in names))
    execution_files = {'started.json', 'openai-decisions.json', 'retained-before-grok.json', 'no-retained-proposals.json',
                       'grok-review.json', 'bank.json', 'bindings.json', 'singles.json', 'complete.json'}
    artifacts = {name for name in execution_files if (folder / name).exists()}
    raw_paths = list((run / 'rounds').glob('phase-f-*.*.json'))
    if not (folder / 'approval.json').exists():
        _require(not names and not paths and not artifacts and not raw_paths and not (folder / 'protocol.json').exists(),
                 'unapproved phase has execution artifacts')
        return result
    approval = _read(folder / 'approval.json')
    expected_approval = {'authorized': True, 'phase': 'F', 'plan_sha256': PLAN_SHA, 'max_new_calls': 2,
                         'max_new_distinct': 300, 'global_budget_usd': 1.5, 'max_output_tokens': 4500, 'new_claude_calls': 0}
    _require(all(approval.get(k) == v for k, v in expected_approval.items()), 'approval differs from frozen scope')
    result.update(state='approved_not_started', approval=approval)
    if not (folder / 'protocol.json').exists():
        _require(not names and not paths and not artifacts and not raw_paths, 'execution exists without activated protocol')
        return result
    protocol = _read(folder / 'protocol.json')
    _require(protocol.get('status') == 'activated' and protocol.get('approval') == approval
             and all(protocol.get(k) == v for k, v in plan.items() if k != 'status'), 'activated protocol differs from frozen plan')
    _bound_files(code_root, protocol['runner_sha256'], RUNNERS)
    _require(_time(plan['created_at']) <= _time(approval['authorized_at']) <= _time(protocol['activated_at']), 'activation chronology differs')
    if not (folder / 'started.json').exists():
        _require(not names and not paths and not artifacts and not raw_paths, 'execution exists without a start record')
        return result
    start = _read(folder / 'started.json')
    _require(start.get('parent_sha256') == parent['sha256'] and start.get('fixed_proposals') == 23
             and _time(protocol['activated_at']) <= _time(start['at']), 'start record differs from fixed input/activation')
    result['state'] = 'running_or_incomplete'
    _require(not ('phase-f-grok' in names and 'phase-f-openai' not in names), 'Grok called without the first review')
    for path in raw_paths:
        _require(path.name.rsplit('.', 2)[0] in names, 'raw request/response exists outside ledger')
    answers, prompts = {}, {}
    incomplete, invalid_response = False, False
    for name, who in [('phase-f-openai', 'openai'), ('phase-f-grok', 'xai')]:
        if name not in names:
            continue
        entry = requests[name]
        _require(entry.get('provider') == who and entry.get('model') == MODELS[who]
                 and _time(entry['started_at']) >= _time(start['at']), 'ledger provider or request chronology differs')
        req_path, res_path = (run / f'rounds/{name}.{kind}.json' for kind in ('request', 'response'))
        if (run / f'rounds/{name}.failure.json').exists():
            _require(_read(run / f'rounds/{name}.failure.json').get('reservation_retained') is True,
                     'failed call has no retained-charge record')
            invalid_response = True
        if not req_path.exists():
            _require(not res_path.exists() and not paths and not (artifacts - {'started.json'})
                     and name == names[-1], 'downstream artifacts lack the request evidence')
            incomplete = True
            continue
        request = _read(req_path)
        _require(entry.get('fingerprint') == _sha(json.dumps(request, sort_keys=True)), 'ledger/request fingerprint differs')
        prompts[who] = _request(request, who, source, claims, parent)
        if who == 'openai':
            _require(prompts[who] == prompt, 'actual OpenAI prompt differs from frozen prompt')
        if not res_path.exists():
            incomplete = True
            continue
        receipt = _read(res_path)
        try:
            answers[who] = _response(receipt, who)
        except (ValueError, TypeError, KeyError):
            incomplete = True
            invalid_response = True
            continue
        _require(entry.get('status') == 'response_saved', 'completed response lacks saved ledger state')
        if 'actual_usd' in entry or (who == 'openai' and 'phase-f-grok' in names):
            _actual_usage(entry, receipt, who)
        result['completed_provider_calls'] += 1
    if incomplete:
        _require(not paths and not (artifacts & {'bank.json', 'bindings.json', 'singles.json', 'complete.json'}),
                 'candidate artifacts depend on an incomplete provider response')
        result['state'] = 'stopped_invalid_or_incomplete_response' if invalid_response else 'running_or_incomplete'
        return result
    if 'openai' not in answers:
        _require(not paths and not (artifacts - {'started.json'}), 'downstream artifacts exist without OpenAI response')
        return result
    _require('openai-decisions.json' in artifacts and _read(folder / 'openai-decisions.json') == answers['openai'],
             'saved decisions differ from the raw OpenAI response')
    try:
        retained = _decisions(parent, proposals, answers['openai'], valid_patch)
    except (ValueError, TypeError, KeyError):
        _require(not paths and not (artifacts - {'started.json', 'openai-decisions.json'}) and 'phase-f-grok' not in names,
                 'downstream artifacts depend on invalid exhaustive decisions')
        result['state'] = 'stopped_invalid_or_incomplete_response'
        return result
    _require(_read(folder / 'retained-before-grok.json') == {'patches': retained, 'all_proposals_decided': 23},
             'retained patches differ from exhaustive decisions')
    result['retained_proposals'] = len(retained)
    if not retained:
        note = _read(folder / 'no-retained-proposals.json')
        _require(note.get('new_unique') == 0 and note.get('grok_called') is False and not paths
                 and 'phase-f-grok' not in names and not (artifacts & {'bank.json', 'grok-review.json', 'bindings.json', 'singles.json', 'complete.json'}),
                 'all-rejected branch produced further work')
        result['state'] = 'all_proposals_rejected'
        return result
    if 'xai' not in answers:
        _require(not paths and not (artifacts & {'bank.json', 'bindings.json', 'singles.json', 'complete.json', 'grok-review.json'}),
                 'candidate artifacts exist without the second review')
        return result
    _require(prompts['xai'].get('patches') == retained
             and _read(folder / 'grok-review.json') == answers['xai'], 'Grok chain differs from exact retained patches/raw response')
    try:
        approved = _review(claims, retained, answers['xai'])
    except (ValueError, TypeError, KeyError):
        _require(not paths and not (artifacts & {'bank.json', 'bindings.json', 'singles.json', 'complete.json'}),
                 'candidate artifacts depend on an invalid second review')
        result['state'] = 'stopped_invalid_or_incomplete_response'
        return result
    bank = _read(folder / 'bank.json')
    _require(bank == {'parent': parent, 'patches': approved, 'source_sha256': _sha(source)}, 'bank differs from exact provider-approved patches')
    expected_bindings = {f'phase-f/{name}.json' for name in ('bank', 'openai-decisions', 'retained-before-grok', 'grok-review')} | {
        f'rounds/phase-f-{name}.{kind}.json' for name in ('openai', 'grok') for kind in ('request', 'response')}
    _bound_files(run, _read(folder / 'bindings.json'), expected_bindings)
    jobs = [_read(p) for p in paths]
    _require(len(jobs) <= 300 and len({j['id'] for j in jobs}) == len(jobs)
             and len({j['sha256'] for j in jobs}) == len(jobs), 'candidate cap or uniqueness differs')
    known_hashes = {_sha(source), *[j['sha256'] for j in previous]}
    for name in ('baseline.json', 'source-original.json'):
        if (run / name).exists():
            known_hashes.add(_read(run / name)['sha256'])
    history = _read(code_root / 'static/research-ten-trials.json')
    for item in [history['original'], history['baseline'], history['selected'], *history['trials'], *history['repairs']]:
        if item.get('sha256'):
            known_hashes.add(item['sha256'])
    _require(not (known_hashes & {j['sha256'] for j in jobs}), 'candidate duplicates historical/prior/source text')
    patches = {p['id']: p for p in approved}
    single_text = {p['id']: _apply(parent['text'], [p]) for p in approved}
    single_pairs = {}
    base = [_logit(pair[d]['measurement']['ai_score']) for d, _ in DETECTORS]
    for job in jobs:
        patch_ids = job.get('patch_ids', [])
        _require(job.get('phase') == 'F' and job.get('source_sha256') == _sha(source)
                 and job.get('parent_id') == parent['id'] and job.get('parent_sha256') == parent['sha256']
                 and patch_ids and len(set(patch_ids)) == len(patch_ids) and all(i in patches for i in patch_ids),
                 'candidate source/parent/patch identity differs')
        text = _apply(parent['text'], [patches[i] for i in patch_ids])
        _require(job.get('text') == text and job.get('sha256') == _sha(text) and clean(text)
                 and numbers(text) == numbers(source) and text.split('\n')[0] == source.split('\n')[0]
                 and text.count(source.split('\n')[0]) == 1, 'candidate exact reconstruction or protected content differs')
        if re.fullmatch(r'f01-s\d{3}', job['id']):
            _require(len(patch_ids) == 1 and 'ranking_only_predicted_logits' not in job, 'single-patch identity differs')
        elif re.fullmatch(r'f01-c\d{3}', job['id']):
            _require(2 <= len(patch_ids) <= 8 and job.get('prediction_is_not_a_measurement') is True,
                     'combination lacks rank-only prediction labeling')
            for p in approved:
                if p['id'] not in single_pairs:
                    single_pairs[p['id']] = load_pair(run, _sha(single_text[p['id']]))
                _require(single_pairs[p['id']] is not None, 'combination lacks exact paired single-patch inputs')
            prediction = list(base)
            for pid in patch_ids:
                prediction = [value + (_logit(single_pairs[pid][d]['measurement']['ai_score']) - original)
                              for value, original, (d, _) in zip(prediction, base, DETECTORS)]
            _require(job.get('ranking_only_predicted_logits') == prediction, 'prediction differs from exact single-patch logit differences')
        else:
            raise ValueError('Phase F unknown candidate ID schema')
    singles = _read(folder / 'singles.json')
    own = {j['id']: j for j in jobs}
    new_singles = [j['id'] for j in jobs if re.fullmatch(r'f01-s\d{3}', j['id'])]
    _require(singles.get('approved_patches') == len(approved) and len(singles.get('singles', [])) == len(approved)
             and singles.get('new_unique') == len(new_singles) and singles.get('candidate_ids') == new_singles,
             'single-patch manifest/count differs')
    for row, patch in zip(singles['singles'], approved):
        digest = _sha(single_text[patch['id']])
        _require(row.get('patch_id') == patch['id'] and row.get('sha256') == digest, 'single-patch manifest hash differs')
        if row.get('job_id'):
            _require(row['job_id'] in own and own[row['job_id']]['sha256'] == digest
                     and re.fullmatch(r'f01-s\d{3}', row['job_id']), 'single-patch manifest job differs')
        else:
            _require(digest in known_hashes and load_pair(run, digest) is not None, 'reused single lacks exact prior measurements')
    combinations = [j['id'] for j in jobs if re.fullmatch(r'f01-c\d{3}', j['id'])]
    if (folder / 'complete.json').exists():
        completion = _read(folder / 'complete.json')
        _require(completion.get('unique_generated') == len(jobs) and completion.get('new_combinations') == len(combinations)
                 and completion.get('candidate_ids') == combinations, 'combination completion manifest/count differs')
    paired = sum(load_pair(run, j['sha256']) is not None for j in jobs)
    result.update(jobs=jobs, approved_patches=len(approved), unique_generated=len(jobs), paired=paired,
                  completed_patch_banks=1,
                  state='complete' if (folder / 'complete.json').exists() and paired == len(jobs) else 'measuring' if jobs else 'bank_ready')
    return result
