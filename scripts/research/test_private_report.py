import hashlib
import json
from pathlib import Path

import pytest

from scripts.research.private_report import DESK_REV, VANG_REV, approvals, build_data, render


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def review(sha, source_hash, who):
    return {'sha256':sha, 'source_sha256':source_hash, 'reviewer':who, 'eligible':True, 'issues':[], 'reviewed_blind_to_scores':True,
        'claim_results':[{'id':f'G{i:02d}','status':'preserved','reason':'Verified source claim.'} for i in range(1,33)],
        'whole_source_review':{name:False for name in ('unsupported_additions','qualification_or_uncertainty_loss','causality_changes','quality_issues')}}


def score(run, sha, d, value):
    revision = DESK_REV if d == 'desklib' else VANG_REV
    m = {'ai_score':value, 'model':'desklib/ai-text-detector-v1.01' if d == 'desklib' else 'ShantanuT01/vanguard-ai-text-detector', 'coverage':'full_document', 'tokens_assessed':1}
    if d == 'desklib':
        m.update(version=revision, precision='bfloat16 matrix storage; float32 compute', sections=[{'weight':1, 'ai_score':value}])
    else:
        m.update(revision=revision, dtype='float32', reference_compile=False, attention='sdpa')
    write(run/'scores'/d/(sha+'.json'), {'sha256':sha,'revision':revision,'measurement':m})


@pytest.fixture
def study(tmp_path):
    source = 'Synthetic example source.'; source_hash=digest(source)
    (tmp_path/'source.txt').write_text(source)
    claims=[{'id':f'G{i:02d}','text':'Fixture claim'} for i in range(1,33)]
    write(tmp_path/'claims.json',claims)
    baseline={'id':'initial','text':'Reviewed starting example.','sha256':digest('Reviewed starting example.'),'source_sha256':source_hash}
    write(tmp_path/'baseline.json',baseline)
    write(tmp_path/'protocol.json',{'source_sha256':source_hash,'initial_parent':baseline,'detectors':{'desklib':{'revision':DESK_REV,'model':'desklib/ai-text-detector-v1.01'},'vanguard':{'revision':VANG_REV,'model':'ShantanuT01/vanguard-ai-text-detector'}}})
    write(tmp_path/'source-bindings.json',{'source_sha256':source_hash,'claims_sha256':digest(json.dumps(claims,sort_keys=True)),'initial_parent_sha256':baseline['sha256']})
    write(tmp_path/'ledger.json',{'limit_usd':1.5,'requests':{'r1':{'status':'response_saved','actual_usd':0.1,'reserved_usd':0.2}}})
    write(tmp_path/'rounds/r01-complete.json',{'status':'generated'})
    for detector in ('desklib','vanguard'):
        score(tmp_path,source_hash,detector,0.9)
    for candidate, text, values in [('approved','Reviewed example output.',(.2,.1)),('pending','Provisional example output.',(.01,.01))]:
        sha=digest(text)
        write(tmp_path/f'jobs/{candidate}.json',{'id':candidate,'text':text,'sha256':sha,'source_sha256':source_hash,'parent_id':'initial','parent_sha256':baseline['sha256']})
        for detector,value in zip(('desklib','vanguard'),values):score(tmp_path,sha,detector,value)
        if candidate=='approved':
            for i in (1,2):write(tmp_path/f'reviews/approved-{i}.json',review(sha,source_hash,f'agent-{i}'))
    return tmp_path


def test_unaudited_lower_scores_never_promote_and_thresholds_are_strict(study):
    data=build_data(study)
    assert data['selected']['job']['id']=='approved'
    assert data['thresholds']=={'30':True,'10':False,'2':False}
    assert data['unique_candidates']==2 and data['paired_candidates']==2 and data['reviewed_candidates']==1
    assert data['estimated_or_reserved_usd']=='0.1'


def test_copy_of_same_reviewer_is_not_an_independent_second_approval(study):
    path=study/'reviews/approved-2.json';data=json.loads(path.read_text());data['reviewer']='agent-1';write(path,data)
    with pytest.raises(ValueError,match='two independent'):
        build_data(study)


def test_changed_candidate_text_fails_closed(study):
    path=study/'jobs/approved.json';data=json.loads(path.read_text());data['text']+=' Added text.';write(path,data)
    with pytest.raises(ValueError,match='hash mismatch'):
        build_data(study)


def test_partial_detector_coverage_fails_closed(study):
    candidate=json.loads((study/'jobs/approved.json').read_text())
    path=study/'scores/desklib'/(candidate['sha256']+'.json');data=json.loads(path.read_text());data['measurement']['coverage']='partial';write(path,data)
    with pytest.raises(ValueError,match='coverage'):
        build_data(study)


def test_missing_original_score_does_not_fall_back_to_unpinned_history(study):
    source_hash=digest((study/'source.txt').read_text());(study/'scores/vanguard'/(source_hash+'.json')).unlink()
    with pytest.raises(ValueError,match='Fresh exact-text source measurements'):
        build_data(study)


def test_failed_whole_source_review_cannot_qualify(study):
    path=study/'reviews/approved-2.json';data=json.loads(path.read_text());data['whole_source_review']['causality_changes']=True;write(path,data)
    with pytest.raises(ValueError,match='two independent'):
        build_data(study)


def test_report_escapes_text_and_embedded_evidence(study):
    data=build_data(study)
    data['source']='Text </script><script>alert(1)</script> end'
    output=render(data)
    assert '&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;' in output
    assert '\\u003c/script\\u003e' in output
    assert '</script><script>alert(1)' not in output
    assert 'src="http' not in output and 'href="http' not in output


def test_phase_b_requires_activation_and_frozen_bank_identity(tmp_path):
    from scripts.research.private_report import phase_b_jobs
    write(tmp_path/'phase-b/jobs/b01-c0001.json', {'phase':'B'})
    write(tmp_path/'phase-b/protocol.json', {'status':'prospective_not_activated'})
    with pytest.raises(ValueError, match='separate activation'):
        phase_b_jobs(tmp_path)


def test_phase_b_reconstructs_text_and_keeps_prediction_distinct(tmp_path):
    from scripts.research.private_report import phase_b_jobs
    parent={'id':'p1','sha256':digest('parent'),'text':'parent'}
    bank={'parent':parent,'patches':[{'id':'x1','start':0,'end':6,'find':'parent','replace':'changed'}]}
    bindings={}
    for bank_id in ['r01','r02']:
        for suffix in ['bank','review','grok.request','grok.response']:
            name=f'{bank_id}-{suffix}.json';path=tmp_path/'rounds'/name
            write(path,bank if suffix=='bank' else {'fixture':'frozen'})
            bindings[name]=digest(path.read_text())
    write(tmp_path/'phase-b/protocol.json',{'status':'activated','phase':'B','new_api_calls':0,'approval':{'authorized':True,'phase':'B','max_new_unique':1000,'banks':['r01','r02']},'frozen_banks':['r01','r02'],'frozen_bank_file_sha256':bindings})
    job={'id':'b1','phase':'B','bank':'r01','parent_id':'p1','parent_sha256':parent['sha256'],'patch_ids':['x1'],'text':'changed','prediction_is_not_a_measurement':True,'ranking_only_predicted_logits':[-100,-100]}
    write(tmp_path/'phase-b/jobs/b1.json',job)
    assert phase_b_jobs(tmp_path)==[job]
    assert 'scores' not in phase_b_jobs(tmp_path)[0]
    job['text']='Unrecorded mutation';write(tmp_path/'phase-b/jobs/b1.json',job)
    with pytest.raises(ValueError,match='full text differs'):
        phase_b_jobs(tmp_path)
