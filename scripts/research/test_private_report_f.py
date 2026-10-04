"""Synthetic fixtures only: no private research text is stored in these tests."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.research import private_report_f as report
from scripts.research.recovery import DESK_REV, VANG_REV, valid_patch


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True))


def scores(run, digest, value=.08):
    for detector, revision, model in [('desklib', DESK_REV, 'desklib/ai-text-detector-v1.01'),
                                       ('vanguard', VANG_REV, 'ShantanuT01/vanguard-ai-text-detector')]:
        m = {'model': model, 'coverage': 'full_document', 'tokens_assessed': 1, 'ai_score': value}
        if detector == 'desklib':
            m.update(version=revision, precision='bfloat16 matrix storage; float32 compute', sections=[{'weight': 1, 'ai_score': value}])
        else:
            m.update(revision=revision, dtype='float32', reference_compile=False, attention='sdpa')
        write(run / 'scores' / detector / (digest + '.json'), {'sha256': digest, 'revision': revision, 'measurement': m})


def response(answer, provider):
    payload = json.dumps(answer)
    if provider == 'anthropic':
        body = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': payload}]}
    else:
        body = {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': payload}]}]}
    return {'http_status': 200, 'body': body}


@pytest.fixture
def study(tmp_path, monkeypatch):
    run, code = tmp_path / 'run', tmp_path / 'code'
    run.mkdir(); code.mkdir(); folder = run / 'phase-f'; folder.mkdir()
    letters = [chr(97 + i) for i in range(23)]
    paragraphs = ['The sample observation named ' + name + ' remains unchanged.' for name in letters]
    source = 'Synthetic report fixture\n\n' + '\n\n'.join(paragraphs)
    parent = {'id': 'd03-s005', 'phase': 'D', 'bank': 3, 'text': source,
              'sha256': sha(source), 'source_sha256': sha(source)}
    claims = [{'id': f'G{i:02d}', 'statement': 'Synthetic fixture claim.'} for i in range(1, 33)]
    previous = [parent]
    scores(run, parent['sha256'])
    for i in (1, 2):
        write(run / f'reviews/parent-{i}.json', {'sha256': parent['sha256'], 'source_sha256': sha(source),
            'eligible': True, 'issues': [], 'reviewer': f'reviewer-{i}', 'reviewed_blind_to_scores': True,
            'claim_results': [{'id': x['id'], 'status': 'preserved', 'reason': 'Fixture reviewed.'} for x in claims],
            'whole_source_review': {k: False for k in ('unsupported_additions', 'qualification_or_uncertainty_loss', 'causality_changes', 'quality_issues')}})
    for i in range(58):
        text = f'Prior E fixture {i}'
        job = {'id': f'e01-c{i:03d}', 'phase': 'E', 'text': text, 'sha256': sha(text), 'source_sha256': sha(source)}
        write(run / 'phase-e/jobs' / (job['id'] + '.json'), job); scores(run, job['sha256']); previous.append(job)
    frozen = {}; reconstructed = {}
    for n, indices in [(1, range(14)), (2, range(11, 23))]:
        path = run / f'phase-e/banks/e{n:02d}/context.json'; write(path, {'parent': parent})
        frozen[str(path.relative_to(run))] = sha(path.read_text())
        cp = {'patches': [{'id': f'bank{n}-{i}', 'find': paragraphs[i],
                           'replace': 'The sample observation named ' + letters[i] + ' is still unchanged.'} for i in indices]}
        for suffix, who, answer in [('claude', 'anthropic', cp), ('openai', 'openai', {'patches': []})]:
            prompt = {'source': source, 'claims': claims, 'current': source}
            if who == 'openai': prompt['proposed'] = cp
            request = {'provider': who, 'model': report.MODELS[who], 'max_output_tokens': 4500, 'prompt': json.dumps(prompt)}
            for kind, value in [('request', request), ('response', response(answer, who))]:
                path = run / f'rounds/phase-e-r{n:02d}-{suffix}.{kind}.json'; write(path, value)
                frozen[str(path.relative_to(run))] = sha(path.read_text())
        for p in cp['patches']:
            patch = valid_patch(source, p)
            reconstructed.setdefault((p['find'], p['replace']), {'patch': patch, 'origins': []})['origins'].append(
                {'bank': n, 'original_proposal_id': p['id']})
    proposals = [{**v['patch'], 'id': f'f-p{i:03d}', 'claude_origins': v['origins']}
                 for i, v in enumerate(reconstructed.values(), 1)]
    write(folder / 'cached-proposals.json', {'parent': parent, 'source_sha256': sha(source),
          'frozen_e_file_sha256': frozen, 'proposals': proposals})
    prompt = {'source': source, 'claims': claims, 'current': source,
              'proposals': [{k: v for k, v in p.items() if k != 'claude_origins'} for p in proposals]}
    write(folder / 'prospective-openai-prompt.json', prompt)
    shared = {}
    for relative in report.SHARED | report.RUNNERS:
        path = code / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('synthetic frozen helper\n')
        if relative in report.SHARED: shared[relative] = sha(path.read_text())
    plan = {'created_at': '2026-10-04T00:00:00+00:00', 'status': 'prospective_not_authorized', 'phase': 'F',
        'source_sha256': sha(source), 'parent_id': parent['id'], 'parent_sha256': parent['sha256'],
        'frozen_shared_code_sha256': shared, 'frozen_e_file_sha256': frozen,
        'cached_proposals_sha256': sha((folder / 'cached-proposals.json').read_text()),
        'prospective_openai_prompt_sha256': sha((folder / 'prospective-openai-prompt.json').read_text())}
    write(folder / 'plan-draft.json', plan); monkeypatch.setattr(report, 'PLAN_SHA', sha(json.dumps(plan, sort_keys=True)))
    write(run / 'ledger.json', {'limit_usd': 1.5, 'requests': {}})
    write(code / 'static/research-ten-trials.json', {'original': {'sha256': sha(source)}, 'baseline': {}, 'selected': {}, 'trials': [], 'repairs': []})
    return {'run': run, 'code': code, 'folder': folder, 'source': source, 'claims': claims,
            'parent': parent, 'previous': previous, 'proposals': proposals, 'plan': plan, 'prompt': prompt}


def build(s):
    return report.phase_f_data(s['run'], s['source'], s['claims'], s['previous'], code_root=s['code'])


def activate(s):
    approval = {'authorized': True, 'phase': 'F', 'plan_sha256': report.PLAN_SHA, 'max_new_calls': 2,
                'max_new_distinct': 300, 'global_budget_usd': 1.5, 'max_output_tokens': 4500, 'new_claude_calls': 0,
                'authorized_at': '2026-10-04T00:01:00+00:00'}
    write(s['folder'] / 'approval.json', approval)
    write(s['folder'] / 'protocol.json', {**s['plan'], 'status': 'activated', 'approval': approval,
          'activated_at': '2026-10-04T00:02:00+00:00', 'runner_sha256': {p: sha((s['code'] / p).read_text()) for p in report.RUNNERS}})
    write(s['folder'] / 'started.json', {'at': '2026-10-04T00:03:00+00:00',
          'parent_sha256': s['parent']['sha256'], 'fixed_proposals': 23})


def call(s, who, prompt, answer=None):
    name = 'phase-f-' + ('grok' if who == 'xai' else 'openai')
    request = {'provider': who, 'model': report.MODELS[who], 'max_output_tokens': 4500, 'prompt': json.dumps(prompt)}
    write(s['run'] / f'rounds/{name}.request.json', request)
    ledger = json.loads((s['run'] / 'ledger.json').read_text())
    ledger['requests'][name] = {'provider': who, 'model': report.MODELS[who], 'reserved_usd': .05,
        'fingerprint': sha(json.dumps(request, sort_keys=True)), 'status': 'reserved', 'started_at': '2026-10-04T00:04:00+00:00'}
    if answer is not None:
        receipt = response(answer, who); receipt['body']['usage'] = {'input_tokens': 100, 'output_tokens': 100}
        write(s['run'] / f'rounds/{name}.response.json', receipt)
        ledger['requests'][name].update(status='response_saved', usage=receipt['body']['usage'],
                                       actual_usd=.0008 if who == 'xai' else .0012)
    write(s['run'] / 'ledger.json', ledger)


def bank(s, *, combinations=True):
    activate(s)
    answer = {'decisions': [{'id': p['id'], 'action': 'accept' if i < 2 else 'reject', 'reason': 'Explicit fixture decision.'}
                           for i, p in enumerate(s['proposals'])]}
    call(s, 'openai', s['prompt'], answer); write(s['folder'] / 'openai-decisions.json', answer)
    retained = [valid_patch(s['source'], p) for p in s['proposals'][:2]]
    write(s['folder'] / 'retained-before-grok.json', {'patches': retained, 'all_proposals_decided': 23})
    review = {'baseline_faithful': True, 'baseline_issues': [], 'checked_claim_ids': [x['id'] for x in s['claims']],
              'patches': [{'id': p['id'], 'faithful': True, 'issues': []} for p in retained]}
    prompt = {'source': s['source'], 'claims': s['claims'], 'current': s['source'], 'patches': retained}
    call(s, 'xai', prompt, review); write(s['folder'] / 'grok-review.json', review)
    write(s['folder'] / 'bank.json', {'parent': s['parent'], 'source_sha256': sha(s['source']), 'patches': retained})
    files = [f'phase-f/{n}.json' for n in ('bank', 'openai-decisions', 'retained-before-grok', 'grok-review')] + [
        f'rounds/phase-f-{n}.{k}.json' for n in ('openai', 'grok') for k in ('request', 'response')]
    write(s['folder'] / 'bindings.json', {p: sha((s['run'] / p).read_text()) for p in files})
    singles = []
    for i, p in enumerate(retained, 1):
        text = report._apply(s['source'], [p]); cid = f'f01-s{i:03d}'
        job = {'id': cid, 'phase': 'F', 'text': text, 'sha256': sha(text), 'source_sha256': sha(s['source']),
               'parent_id': s['parent']['id'], 'parent_sha256': s['parent']['sha256'], 'patch_ids': [p['id']]}
        write(s['folder'] / f'jobs/{cid}.json', job); scores(s['run'], sha(text))
        singles.append({'patch_id': p['id'], 'sha256': sha(text), 'job_id': cid, 'new_unique': True})
    write(s['folder'] / 'singles.json', {'approved_patches': 2, 'singles': singles, 'new_unique': 2,
          'candidate_ids': [x['job_id'] for x in singles]})
    if combinations:
        text = report._apply(s['source'], retained); cid = 'f01-c001'
        write(s['folder'] / f'jobs/{cid}.json', {'id': cid, 'phase': 'F', 'text': text, 'sha256': sha(text),
            'source_sha256': sha(s['source']), 'parent_id': s['parent']['id'], 'parent_sha256': s['parent']['sha256'],
            'patch_ids': [p['id'] for p in retained], 'prediction_is_not_a_measurement': True,
            'ranking_only_predicted_logits': [report._logit(.08), report._logit(.08)]})
        scores(s['run'], sha(text)); write(s['folder'] / 'complete.json', {'unique_generated': 3, 'new_combinations': 1, 'candidate_ids': [cid]})


def test_proposed_phase_reports_zero_tests_and_calls(study):
    before = {str(p): p.read_bytes() for p in study['run'].rglob('*') if p.is_file()}
    result = build(study)
    assert result['state'] == 'proposed' and result['jobs'] == []
    assert result['new_provider_requests'] == result['unique_generated'] == result['paired'] == result['completed_patch_banks'] == 0
    assert (result['cached_origin_count'], result['cached_proposal_count']) == (26, 23)
    assert before == {str(p): p.read_bytes() for p in study['run'].rglob('*') if p.is_file()}


def test_no_approval_cannot_hide_a_paid_request(study):
    call(study, 'openai', study['prompt'])
    with pytest.raises(ValueError, match='unapproved'): build(study)


def test_changed_frozen_cache_is_rejected(study):
    path = study['run'] / 'rounds/phase-e-r01-claude.response.json'; path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='frozen file'): build(study)


def test_e58_requires_both_exact_receipts(study):
    digest = study['previous'][1]['sha256']; (study['run'] / f'scores/vanguard/{digest}.json').unlink()
    with pytest.raises(ValueError, match='E prerequisite'): build(study)


def test_parent_needs_two_distinct_reviews(study):
    path = study['run'] / 'reviews/parent-2.json'; x = json.loads(path.read_text()); x['reviewer'] = 'reviewer-1'; write(path, x)
    with pytest.raises(ValueError, match='two complete approvals'): build(study)


def test_pending_call_remains_pending_and_reserved(study):
    activate(study); call(study, 'openai', study['prompt'])
    result = build(study)
    assert result['state'] == 'running_or_incomplete' and result['jobs'] == []
    assert result['new_provider_requests'] == result['unknown_cost_requests'] == 1
    assert result['estimated_or_reserved_usd'] == '0.05'


def test_changed_activated_runner_is_rejected(study):
    activate(study); (study['code'] / 'scripts/research/phase_f.py').write_text('changed helper')
    with pytest.raises(ValueError, match='frozen file'): build(study)


def test_invalid_exhaustive_coverage_stops_without_candidates(study):
    activate(study); answer = {'decisions': []}; call(study, 'openai', study['prompt'], answer)
    write(study['folder'] / 'openai-decisions.json', answer)
    result = build(study)
    assert result['state'] == 'stopped_invalid_or_incomplete_response' and result['jobs'] == []


def test_valid_exact_bank_and_combination(study):
    bank(study); result = build(study)
    assert result['state'] == 'complete' and result['unique_generated'] == result['paired'] == 3
    assert result['new_provider_requests'] == 2 and result['completed_patch_banks'] == 1
    assert 'thresholds' not in result  # Promotion remains the outer report's two-review gate.


def test_changed_combination_prediction_cannot_be_reported_as_evidence(study):
    bank(study); path = study['folder'] / 'jobs/f01-c001.json'; x = json.loads(path.read_text())
    x['ranking_only_predicted_logits'] = [-100, -100]; write(path, x)
    with pytest.raises(ValueError, match='prediction differs'): build(study)


def test_changed_candidate_text_is_rejected(study):
    bank(study); path = study['folder'] / 'jobs/f01-c001.json'; x = json.loads(path.read_text())
    x['text'] += ' New statement.'; x['sha256'] = sha(x['text']); write(path, x)
    with pytest.raises(ValueError, match='exact reconstruction'): build(study)


def test_prior_duplicate_never_counts_as_new(study):
    bank(study); x = json.loads((study['folder'] / 'jobs/f01-c001.json').read_text())
    study['previous'].append({**x, 'id': 'prior-a', 'phase': 'A'})
    with pytest.raises(ValueError, match='duplicates historical'): build(study)


def test_missing_single_measurement_blocks_combination(study):
    bank(study); x = json.loads((study['folder'] / 'jobs/f01-s001.json').read_text())
    (study['run'] / f'scores/vanguard/{x["sha256"]}.json').unlink()
    with pytest.raises(ValueError, match='paired single-patch'): build(study)


def test_unknown_provider_request_is_rejected(study):
    ledger = json.loads((study['run'] / 'ledger.json').read_text())
    ledger['requests']['phase-f-claude'] = {'reserved_usd': .01}; write(study['run'] / 'ledger.json', ledger)
    with pytest.raises(ValueError, match='request identities'): build(study)


def test_over_budget_is_rejected(study):
    ledger = {'limit_usd': 1.5, 'requests': {'earlier': {'reserved_usd': 1.500001}}}
    write(study['run'] / 'ledger.json', ledger)
    with pytest.raises(ValueError, match='budget exceeds'): build(study)


def test_second_call_requires_actual_first_usage(study):
    bank(study); path = study['run'] / 'ledger.json'; ledger = json.loads(path.read_text())
    del ledger['requests']['phase-f-openai']['actual_usd']; write(path, ledger)
    with pytest.raises(ValueError, match='actual usage'): build(study)


def test_fixed_find_span_cannot_be_changed_in_a_decision(study):
    answer = {'decisions': [{'id': p['id'], 'action': 'reject', 'reason': 'Fixture rejection.'} for p in study['proposals']]}
    answer['decisions'][0]['find'] = 'another span'
    with pytest.raises(ValueError, match='fixed find span'):
        report._decisions(study['parent'], study['proposals'], answer, valid_patch)


def test_grok_rejection_requires_explicit_issue(study):
    patches = [valid_patch(study['source'], study['proposals'][0])]
    review = {'baseline_faithful': True, 'baseline_issues': [], 'checked_claim_ids': [c['id'] for c in study['claims']],
              'patches': [{'id': patches[0]['id'], 'faithful': False, 'issues': []}]}
    with pytest.raises(ValueError, match='explicit rejection issues'):
        report._review(study['claims'], patches, review)
