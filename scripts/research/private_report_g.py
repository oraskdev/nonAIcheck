"""Read-only evidence validation for the separately approved zero-API Phase G.

Frozen ranking rows are candidate proposals, never measurements. This module
returns actual jobs and paired-receipt counts; the main report alone promotes
results after two complete independent source reviews.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[2]
PLAN_SHA = 'f129eb52bb1790db10b5a648e61eebdbdf6e5ce801954bb0f868370a63667ed4'
SHARED = {'scripts/research/recovery.py', 'scripts/research/phase_b.py', 'scripts/research/phase_d.py',
          'scripts/research/phase_e.py', 'scripts/research/phase_f.py', 'scripts/research/score.py'}
RUNNERS = {'scripts/research/phase_g.py', 'scripts/research/score_phase_g.py'}


def _read(path):
    return json.loads(Path(path).read_text())


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError('Phase G ' + message)


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _require(result.tzinfo is not None, 'timestamp lacks timezone')
    return result


def _files(base, mapping, expected):
    _require(isinstance(mapping, dict) and set(mapping) == expected, 'frozen file set differs')
    for relative, digest in mapping.items():
        _require(_sha((base / relative).read_text()) == digest, 'frozen file changed: ' + relative)


def _validated_banks(run, source, claims, previous, code_root):
    """Reuse existing read-only receipt validators, never runner admission helpers."""
    from scripts.research.private_report import phase_e_jobs
    from scripts.research.private_report_f import phase_f_data
    prior_e = [j for j in previous if j.get('phase') not in ('E', 'F', 'G')]
    ejobs = phase_e_jobs(run, source, claims, prior_e)
    fdata = phase_f_data(run, source, claims, prior_e + ejobs, code_root=code_root)
    expected = {j['id']: j for j in previous if j.get('phase') in ('E', 'F')}
    _require({j['id']: j for j in ejobs + fdata['jobs']} == expected, 'previous E/F jobs differ from validated evidence')
    return [('e01', _read(run / 'phase-e/banks/e01/bank.json')),
            ('e02', _read(run / 'phase-e/banks/e02/bank.json')),
            ('f01', _read(run / 'phase-f/bank.json'))]


def _apply(text, patches):
    ordered = sorted(patches, key=lambda p: p['start'])
    _require(not any(a['end'] > b['start'] for a, b in zip(ordered, ordered[1:])), 'candidate patches overlap')
    for patch in reversed(ordered):
        _require(text[patch['start']:patch['end']] == patch['find'], 'candidate exact span changed')
        text = text[:patch['start']] + patch['replace'] + text[patch['end']:]
    return text


def _logit(value):
    value = max(1e-7, min(1 - 1e-7, value))
    return math.log(value / (1 - value))


def _selection(rows):
    _require(len(rows) >= 1000, 'ranked pool contains fewer than 1000 proposals')
    rest = list(rows[800:]); random.Random(6100440).shuffle(rest)
    return list(rows[:800]) + rest[:200]


def phase_g_data(run, source, claims, previous, *, code_root=None):
    from scripts.research.private_report import approvals, load_pair, DETECTORS
    from scripts.research.recovery import valid_patch, numbers, clean
    run, code_root = Path(run), Path(code_root or ROOT)
    folder = run / 'phase-g'
    paths = sorted((folder / 'jobs').glob('*.json'))
    book = _read(run / 'ledger.json')
    _require(not any(k.startswith('phase-g-') for k in book['requests'])
             and not list((run / 'rounds').glob('phase-g-*')), 'zero-provider phase contains a provider request/receipt')
    total = Decimal('0')
    for entry in book['requests'].values():
        amount = Decimal(str(entry.get('actual_usd', entry['reserved_usd'])))
        _require(amount.is_finite() and amount >= 0, 'ledger contains an invalid cost')
        total += amount
    _require(book.get('limit_usd') == 1.5 and total <= Decimal('1.50'), 'shared API budget exceeds frozen cap')
    result = {'phase': 'G', 'jobs': [], 'state': 'absent', 'new_provider_requests': 0,
              'completed_patch_banks': 0, 'unique_generated': 0, 'paired': 0, 'approved_patch_count': 0,
              'estimated_or_reserved_usd': '0', 'global_estimated_or_reserved_usd': str(total),
              'scope': 'One-source adaptive research; frozen proposals and predictions are not measured tests.',
              'limits': {'new_provider_calls': 0, 'new_distinct_texts': 1000, 'shared_global_api_usd': 1.5}}
    if not (folder / 'plan-draft.json').exists():
        _require(not paths and not (folder / 'protocol.json').exists()
                 and not (folder / 'approval.json').exists(), 'execution exists without prospective plan')
        return result
    plan = _read(folder / 'plan-draft.json')
    _require(_sha(json.dumps(plan, sort_keys=True)) == PLAN_SHA and plan.get('phase') == 'G'
             and plan.get('source_sha256') == _sha(source), 'fixed prospective plan/source differs')
    _files(code_root, plan['frozen_shared_code_sha256'], SHARED)
    for name, key in [('approved-pool.json', 'approved_pool_sha256'), ('ranked-unused-pool.json', 'ranked_unused_pool_sha256')]:
        _require(_sha((folder / name).read_text()) == plan[key], 'frozen pool/ranking changed')
    pool = _read(folder / 'approved-pool.json')
    parent = pool['parent']; by_id = {j['id']: j for j in previous}
    _require(parent.get('id') == plan.get('parent_id') == 'd03-s005'
             and parent.get('sha256') == plan.get('parent_sha256') == _sha(parent['text'])
             and parent.get('source_sha256') == pool.get('source_sha256') == _sha(source)
             and by_id.get(parent['id']) == parent, 'fixed parent/source/prior identity differs')
    ids = {f'G{i:02d}' for i in range(1, 33)}
    _require(len(claims) == 32 and {c['id'] for c in claims} == ids, 'source claim inventory differs')
    reviews = [(p, _read(p)) for p in sorted((run / 'reviews').glob('*.json'))]
    parent_pair = load_pair(run, parent['sha256'])
    _require(parent_pair is not None and len(approvals(reviews, parent['sha256'], _sha(source), ids)) >= 2,
             'parent lacks exact paired measurements and two complete source approvals')
    banks = _validated_banks(run, source, claims, previous, code_root)
    pooled, frozen = {}, set()
    for name, bank in banks:
        _require(bank.get('parent') == parent and bank.get('source_sha256') == _sha(source), 'pool banks do not share exact parent/source')
        for patch in bank['patches']:
            _require(valid_patch(parent['text'], patch) == patch, 'approved pool patch violates unchanged guards')
            key = (patch['find'], patch['replace'], patch['start'], patch['end'])
            pooled.setdefault(key, {'patch': patch, 'provenance': []})['provenance'].append({'bank': name, 'patch_id': patch['id']})
        letter = name[0]
        base = run / 'phase-e/banks' / name if letter == 'e' else run / 'phase-f'
        binding_path = base / 'bindings.json'
        frozen.update({f'phase-{letter}/{n}.json' for n in ('approval', 'protocol', 'plan-draft')})
        frozen.add(str(binding_path.relative_to(run)))
        frozen.update(_read(binding_path))
    expected = [{**v['patch'], 'id': f'g-p{i:03d}', 'provenance': v['provenance']}
                for i, (_, v) in enumerate(sorted(pooled.items(), key=lambda item: (item[0][2], item[0][3], item[0][0], item[0][1])), 1)]
    _require(len(expected) == 29 == plan.get('approved_patch_count') and pool.get('patches') == expected,
             '29-edit pool/provenance does not reconstruct from reviewed E/F banks')
    _files(run, pool['frozen_bank_files'], frozen)
    patches = pool['patches']
    ranked = _read(folder / 'ranked-unused-pool.json'); rows = ranked['rows']
    _require(ranked.get('count') == len(rows) == plan.get('bounded_unused_distinct_pool')
             and len(rows) >= 1000 and ranked.get('measured_candidates') == 0 and ranked.get('new_provider_calls') == 0
             and len({row['sha256'] for row in rows}) == len(rows), 'ranked proposal count/uniqueness/measurement label differs')
    excluded = {_sha(source), *[j['sha256'] for j in previous]}
    for name in ('baseline.json', 'source-original.json'):
        if (run / name).exists(): excluded.add(_read(run / name)['sha256'])
    historical = _read(code_root / 'static/research-ten-trials.json')
    excluded.update(p['sha256'] for p in [historical['original'], historical['baseline'], historical['selected'],
                                         *historical['trials'], *historical['repairs']] if p.get('sha256'))
    _require(not excluded.intersection(row['sha256'] for row in rows), 'ranked pool duplicates source/history/prior phase')
    single_pairs = []
    for patch in patches:
        single = _apply(parent['text'], [patch]); pair = load_pair(run, _sha(single))
        _require(pair is not None, 'pool patch lacks exact paired single-text measurements')
        single_pairs.append(pair)
    base = [_logit(parent_pair[d]['measurement']['ai_score']) for d, _ in DETECTORS]
    deltas = [[_logit(pair[d]['measurement']['ai_score']) - original
               for original, (d, _) in zip(base, DETECTORS)] for pair in single_pairs]
    for row in rows:
        indices = row.get('indices', [])
        _require(isinstance(indices, list) and 2 <= len(indices) <= 10
                 and all(type(i) is int and 0 <= i < 29 for i in indices) and indices == sorted(set(indices))
                 and row.get('prediction_is_not_a_measurement') is True, 'ranked combination index/prediction schema differs')
        values = list(base)
        for i in indices:
            values = [v + change for v, change in zip(values, deltas[i])]
        _require(row.get('ranking_only_predicted_logits') == values, 'prediction differs from exact measured single-text inputs')
        chosen = [patches[i] for i in indices]
        _require(not any(a['end'] > b['start'] for a, b in zip(chosen, chosen[1:])), 'ranked combination spans overlap')
        _require(_sha(_apply(parent['text'], chosen)) == row['sha256'], 'ranked proposal exact text/hash differs')
    selected = _selection(rows)
    result.update(state='proposed', plan=plan, approved_patch_count=29,
                  bounded_unused_proposals=len(rows), scope=plan.get('scope', result['scope']))
    if not (folder / 'approval.json').exists():
        _require(not paths and not (folder / 'protocol.json').exists() and not (folder / 'complete.json').exists(),
                 'unapproved phase has generated artifacts')
        return result
    approval = _read(folder / 'approval.json')
    approved = {'authorized': True, 'phase': 'G', 'plan_sha256': PLAN_SHA, 'max_new_unique': 1000,
                'new_api_calls': 0, 'global_budget_usd': 1.5}
    _require(all(approval.get(k) == v for k, v in approved.items()), 'approval differs from fixed zero-API scope')
    result.update(state='approved_not_started', approval=approval)
    if not (folder / 'protocol.json').exists():
        _require(not paths and not (folder / 'complete.json').exists(), 'jobs exist without activation')
        return result
    protocol = _read(folder / 'protocol.json')
    _require(protocol.get('status') == 'activated' and protocol.get('approval') == approval
             and all(protocol.get(k) == v for k, v in plan.items() if k != 'status')
             and protocol.get('selection_sha256') == _sha(json.dumps(selected, sort_keys=True))
             and protocol.get('new_provider_calls') == 0, 'activated plan/selection binding differs')
    _files(code_root, protocol['runner_sha256'], RUNNERS)
    _require(_time(plan['created_at']) <= _time(approval['authorized_at']) <= _time(protocol['activated_at']),
             'activation chronology differs')
    target_paths = [run / 'verified-gate-2.json',
                    *[run / f'phase-{letter}/verified-gate-2.json' for letter in ('b', 'd', 'e', 'f', 'g')]]
    for path in target_paths:
        if path.exists():
            gate = _read(path)
            verified_at = gate.get('verified_at', gate.get('at'))
            _require(isinstance(verified_at, str) and _time(verified_at) > _time(protocol['activated_at']),
                     'below-2 gate already existed at activation')
    final = _read(run / 'phase-f/final-complete.json')
    fjobs = [j for j in previous if j.get('phase') == 'F']
    _require(final.get('phase') == 'F' and final.get('unique_generated') == final.get('paired') == 300
             and len(fjobs) == len({j['sha256'] for j in fjobs}) == 300
             and _time(final['at']) <= _time(protocol['activated_at']), 'activation lacks completed prior F300')
    for job in fjobs:
        _require(job.get('source_sha256') == _sha(source) and _sha(job['text']) == job['sha256']
                 and load_pair(run, job['sha256']) is not None, 'F prerequisite lacks exact paired full texts')
    prior_selected = final.get('selected_verified', {})
    candidate = by_id.get(prior_selected.get('id'))
    _require(candidate in fjobs and candidate['sha256'] == prior_selected.get('sha256'), 'F final selected candidate differs')
    candidate_pair = load_pair(run, candidate['sha256'])
    _require([candidate_pair[d]['measurement']['ai_score'] for d, _ in DETECTORS]
             == [prior_selected.get('desklib'), prior_selected.get('vanguard')]
             and len(approvals(reviews, candidate['sha256'], _sha(source), ids)) >= 2,
             'F final selected result lacks bound exact scores and two approvals')
    jobs = [_read(path) for path in paths]
    _require(len(jobs) <= 1000 and len({j['id'] for j in jobs}) == len(jobs)
             and len({j['sha256'] for j in jobs}) == len(jobs), 'distinct-text cap/uniqueness differs')
    _require(not excluded.intersection(job['sha256'] for job in jobs), 'candidate duplicates source/history/prior phase')
    for index, job in enumerate(jobs, 1):
        row = selected[index - 1]
        _require(job.get('id') == f'g01-c{index:04d}' and job.get('phase') == 'G'
                 and job.get('parent_id') == parent['id'] and job.get('parent_sha256') == parent['sha256']
                 and job.get('source_sha256') == _sha(source)
                 and all(job.get(k) == v for k, v in row.items()), 'job differs from deterministic frozen selection')
        chosen = [patches[i] for i in row['indices']]
        text = _apply(parent['text'], chosen)
        _require(job.get('patch_ids') == [p['id'] for p in chosen] and job.get('text') == text
                 and job.get('sha256') == _sha(text) and clean(text) and numbers(text) == numbers(source)
                 and text.split('\n')[0] == source.split('\n')[0] and text.count(source.split('\n')[0]) == 1,
                 'candidate exact text/hash/protected content differs')
        _require(_time(job['created_at']) >= _time(protocol['activated_at']), 'candidate predates activation')
    if (folder / 'complete.json').exists():
        completion = _read(folder / 'complete.json')
        _require(completion.get('unique_generated') == len(jobs) == 1000 and completion.get('new_api_calls') == 0
                 and _time(completion['at']) >= max(_time(job['created_at']) for job in jobs),
                 'completed generation count/chronology differs')
    paired = sum(load_pair(run, job['sha256']) is not None for job in jobs)
    result.update(jobs=jobs, unique_generated=len(jobs), paired=paired,
                  state='complete' if len(jobs) == paired == 1000 and (folder / 'complete.json').exists()
                  else 'measuring' if jobs else 'active')
    return result
