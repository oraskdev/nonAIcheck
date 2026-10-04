"""Synthetic Phase G fixtures; prior E/F parser contracts have separate tests."""
import itertools
import json

import pytest

from scripts.research import private_report_g as report
from scripts.research.recovery import valid_patch
from scripts.research.test_private_report_f import sha, write, scores


@pytest.fixture
def study(tmp_path, monkeypatch):
    run, code = tmp_path / 'run', tmp_path / 'code'; run.mkdir(); code.mkdir()
    folder = run / 'phase-g'; folder.mkdir()
    names = [chr(97 + i // 26) + chr(97 + i % 26) for i in range(29)]
    paragraphs = ['This sample observation called ' + name + ' remains unchanged.' for name in names]
    source = 'Synthetic G fixture\n\n' + '\n\n'.join(paragraphs)
    parent = {'id': 'd03-s005', 'phase': 'D', 'text': source, 'sha256': sha(source), 'source_sha256': sha(source)}
    claims = [{'id': f'G{i:02d}', 'statement': 'Synthetic source claim.'} for i in range(1, 33)]
    previous = [parent]; scores(run, sha(source))
    patches = [valid_patch(source, {'id': f'p{i:03d}', 'find': p, 'replace': p.replace('remains unchanged', 'is still unchanged')})
               for i, p in enumerate(paragraphs)]
    banks = [('e01', {'parent': parent, 'source_sha256': sha(source), 'patches': patches[:5]}),
             ('e02', {'parent': parent, 'source_sha256': sha(source), 'patches': patches[3:8]}),
             ('f01', {'parent': parent, 'source_sha256': sha(source), 'patches': patches[8:]})]
    # G delegates complete raw approval validation to independently tested E/F parsers.
    monkeypatch.setattr(report, '_validated_banks', lambda *_: banks)
    frozen = {}; pooled = {}
    for name, bank in banks:
        letter = name[0]; base = run / 'phase-e/banks' / name if letter == 'e' else run / 'phase-f'
        write(base / 'bank.json', bank)
        write(base / 'bindings.json', {str((base / 'bank.json').relative_to(run)): sha((base / 'bank.json').read_text())})
        frozen[str((base / 'bank.json').relative_to(run))] = sha((base / 'bank.json').read_text())
        frozen[str((base / 'bindings.json').relative_to(run))] = sha((base / 'bindings.json').read_text())
        for key in ('approval', 'protocol', 'plan-draft'):
            p = run / f'phase-{letter}/{key}.json'; write(p, {'fixture': True}); frozen[str(p.relative_to(run))] = sha(p.read_text())
        for p in bank['patches']:
            key = (p['find'], p['replace'], p['start'], p['end'])
            pooled.setdefault(key, {'patch': p, 'provenance': []})['provenance'].append({'bank': name, 'patch_id': p['id']})
    combined = [{**v['patch'], 'id': f'g-p{i:03d}', 'provenance': v['provenance']}
                for i, (_, v) in enumerate(sorted(pooled.items(), key=lambda item: (item[0][2], item[0][3], item[0][0], item[0][1])), 1)]
    pool = {'parent': parent, 'patches': combined, 'source_sha256': sha(source), 'frozen_bank_files': frozen}
    write(folder / 'approved-pool.json', pool)
    for patch in combined: scores(run, sha(report._apply(source, [patch])))
    indices = sorted([*itertools.combinations(range(29), 2), *itertools.combinations(range(29), 3)])[:1100]
    rows = [{'indices': list(ix), 'sha256': sha(report._apply(source, [combined[i] for i in ix])),
             'ranking_only_predicted_logits': [report._logit(.08)] * 2, 'prediction_is_not_a_measurement': True} for ix in indices]
    write(folder / 'ranked-unused-pool.json', {'at': '2026-10-04T00:02:00+00:00', 'count': len(rows), 'rows': rows,
          'measured_candidates': 0, 'new_provider_calls': 0})
    shared = {}
    for relative in report.SHARED | report.RUNNERS:
        p = code / relative; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('Synthetic frozen helper\n')
        if relative in report.SHARED: shared[relative] = sha(p.read_text())
    plan = {'created_at': '2026-10-04T00:03:00+00:00', 'phase': 'G', 'status': 'prospective_not_authorized',
        'source_sha256': sha(source), 'parent_id': parent['id'], 'parent_sha256': parent['sha256'],
        'frozen_shared_code_sha256': shared, 'approved_pool_sha256': sha((folder / 'approved-pool.json').read_text()),
        'ranked_unused_pool_sha256': sha((folder / 'ranked-unused-pool.json').read_text()),
        'approved_patch_count': 29, 'bounded_unused_distinct_pool': len(rows), 'new_provider_calls': 0}
    write(folder / 'plan-draft.json', plan); monkeypatch.setattr(report, 'PLAN_SHA', sha(json.dumps(plan, sort_keys=True)))
    write(run / 'ledger.json', {'limit_usd': 1.5, 'requests': {}})
    write(code / 'static/research-ten-trials.json', {'original': {'sha256': sha(source)}, 'baseline': {}, 'selected': {}, 'trials': [], 'repairs': []})
    for i in range(300):
        text = f'Prior synthetic F example {i}'
        job = {'id': f'f01-c{i:03d}', 'phase': 'F', 'text': text, 'sha256': sha(text), 'source_sha256': sha(source)}
        previous.append(job); scores(run, job['sha256'])
    candidate = previous[-1]
    write(run / 'phase-f/final-complete.json', {'at': '2026-10-04T00:02:00+00:00', 'phase': 'F', 'unique_generated': 300, 'paired': 300,
        'selected_verified': {'id': candidate['id'], 'sha256': candidate['sha256'], 'desklib': .08, 'vanguard': .08}})
    for who, reviewed in [('parent', parent), ('final', candidate)]:
        for n in (1, 2):
            write(run / f'reviews/{who}-{n}.json', {'sha256': reviewed['sha256'], 'source_sha256': sha(source),
                'eligible': True, 'issues': [], 'reviewer': f'reviewer-{n}', 'reviewed_blind_to_scores': True,
                'claim_results': [{'id': c['id'], 'status': 'preserved', 'reason': 'Synthetic review.'} for c in claims],
                'whole_source_review': {k: False for k in ('unsupported_additions', 'qualification_or_uncertainty_loss', 'causality_changes', 'quality_issues')}})
    return {'run': run, 'code': code, 'folder': folder, 'source': source, 'parent': parent, 'claims': claims,
            'previous': previous, 'plan': plan, 'rows': rows, 'pool': pool}


def build(s):
    return report.phase_g_data(s['run'], s['source'], s['claims'], s['previous'], code_root=s['code'])


def activate(s, count=0, complete=False, measured=False):
    approval = {'authorized': True, 'phase': 'G', 'plan_sha256': report.PLAN_SHA, 'max_new_unique': 1000,
                'new_api_calls': 0, 'global_budget_usd': 1.5, 'authorized_at': '2026-10-04T00:04:00+00:00'}
    write(s['folder'] / 'approval.json', approval)
    selected = report._selection(s['rows'])
    protocol = {**s['plan'], 'status': 'activated', 'approval': approval, 'activated_at': '2026-10-04T00:05:00+00:00',
        'runner_sha256': {p: sha((s['code'] / p).read_text()) for p in report.RUNNERS},
        'selection_sha256': sha(json.dumps(selected, sort_keys=True)), 'new_provider_calls': 0}
    write(s['folder'] / 'protocol.json', protocol)
    for i, row in enumerate(selected[:count], 1):
        patches = [s['pool']['patches'][n] for n in row['indices']]
        job = {**row, 'id': f'g01-c{i:04d}', 'phase': 'G', 'source_sha256': sha(s['source']),
            'parent_id': s['parent']['id'], 'parent_sha256': s['parent']['sha256'],
            'text': report._apply(s['source'], patches), 'patch_ids': [p['id'] for p in patches],
            'created_at': '2026-10-04T00:06:00+00:00'}
        write(s['folder'] / ('jobs/' + job['id'] + '.json'), job)
        if measured: scores(s['run'], job['sha256'])
    if complete:
        write(s['folder'] / 'complete.json', {'at': '2026-10-04T00:07:00+00:00', 'unique_generated': count,
              'new_api_calls': 0, 'scoring': 'pending'})


def test_proposed_ranked_pool_is_not_a_measured_test(study):
    before = {str(p): p.read_bytes() for p in study['run'].rglob('*') if p.is_file()}
    x = build(study)
    assert x['state'] == 'proposed' and x['jobs'] == []
    assert x['unique_generated'] == x['paired'] == x['new_provider_requests'] == x['completed_patch_banks'] == 0
    assert x['approved_patch_count'] == 29 and x['bounded_unused_proposals'] == 1100
    assert before == {str(p): p.read_bytes() for p in study['run'].rglob('*') if p.is_file()}


def test_zero_calls_enforced_before_any_jobs(study):
    write(study['run'] / 'ledger.json', {'limit_usd': 1.5, 'requests': {'phase-g-openai': {'reserved_usd': .01}}})
    with pytest.raises(ValueError, match='zero-provider'): build(study)


def test_orphan_provider_receipt_is_rejected(study):
    write(study['run'] / 'rounds/phase-g-grok.response.json', {})
    with pytest.raises(ValueError, match='zero-provider'): build(study)


def test_frozen_pool_change_fails(study):
    path = study['folder'] / 'approved-pool.json'; path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='frozen pool'): build(study)


def test_parent_requires_two_complete_reviews(study):
    (study['run'] / 'reviews/parent-2.json').unlink()
    with pytest.raises(ValueError, match='two complete source approvals'): build(study)


def test_single_patch_score_is_required_for_predictions(study):
    p = study['pool']['patches'][0]; digest = sha(report._apply(study['source'], [p]))
    (study['run'] / f'scores/vanguard/{digest}.json').unlink()
    with pytest.raises(ValueError, match='paired single-text'): build(study)


def test_active_empty_phase_has_no_measured_results(study):
    activate(study); x = build(study)
    assert x['state'] == 'active' and x['jobs'] == [] and x['paired'] == 0


@pytest.mark.parametrize('relative,key', [('verified-gate-2.json', 'verified_at'),
                                        ('phase-f/verified-gate-2.json', 'at')])
def test_preexisting_below_two_gate_prevents_activation(study, relative, key):
    activate(study)
    write(study['run'] / relative, {key: '2026-10-04T00:05:00+00:00'})
    with pytest.raises(ValueError, match='already existed at activation'):
        build(study)


def test_gate_created_after_activation_does_not_invalidate_report(study):
    activate(study, count=3)
    write(study['folder'] / 'verified-gate-2.json', {'at': '2026-10-04T00:07:00+00:00'})
    assert build(study)['unique_generated'] == 3


def test_partial_generation_has_only_actual_paired_counts(study):
    activate(study, count=3, measured=False); x = build(study)
    assert x['state'] == 'measuring' and x['unique_generated'] == 3 and x['paired'] == 0
    assert 'thresholds' not in x


def test_complete_requires_1000_real_paired_receipts(study):
    activate(study, count=1000, complete=True, measured=True); x = build(study)
    assert x['state'] == 'complete' and x['unique_generated'] == x['paired'] == 1000


def test_changed_job_prediction_rejected(study):
    activate(study, count=1); path = study['folder'] / 'jobs/g01-c0001.json'; x = json.loads(path.read_text())
    x['ranking_only_predicted_logits'] = [-100, -100]; write(path, x)
    with pytest.raises(ValueError, match='deterministic frozen selection'): build(study)


def test_changed_exact_candidate_rejected(study):
    activate(study, count=1); path = study['folder'] / 'jobs/g01-c0001.json'; x = json.loads(path.read_text())
    x['text'] += ' New unsupported text.'; write(path, x)
    with pytest.raises(ValueError, match='exact text/hash'): build(study)


def test_prior_text_cannot_be_recounted(study):
    row = study['rows'][0]
    study['previous'].append({'id': 'prior-a', 'phase': 'A', 'sha256': row['sha256']})
    with pytest.raises(ValueError, match='duplicates source/history'): build(study)


def test_f_selected_score_binding_cannot_change(study):
    activate(study); path = study['run'] / 'phase-f/final-complete.json'; x = json.loads(path.read_text())
    x['selected_verified']['desklib'] = .01; write(path, x)
    with pytest.raises(ValueError, match='F final selected result'): build(study)


def test_f_final_needs_two_reviews(study):
    activate(study); (study['run'] / 'reviews/final-2.json').unlink()
    with pytest.raises(ValueError, match='F final selected result'): build(study)


def test_changed_runner_fails_closed(study):
    activate(study); (study['code'] / 'scripts/research/phase_g.py').write_text('changed implementation')
    with pytest.raises(ValueError, match='frozen file changed'): build(study)


def test_generation_completion_cannot_forge_a_full_count(study):
    activate(study, count=3, complete=True)
    with pytest.raises(ValueError, match='completed generation count'): build(study)
