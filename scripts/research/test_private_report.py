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


@pytest.fixture
def holdout_fixture(tmp_path):
    from scripts.research.private_report import HOLDOUT_FILES
    run=tmp_path/'run'; folder=run/'production-holdout-01'; folder.mkdir(parents=True)
    code=tmp_path/'code'; mapping={}
    for name in HOLDOUT_FILES:
        path=code/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# frozen fixture\n');mapping[name]=digest(path.read_text())
    strategy=digest(json.dumps(mapping,sort_keys=True,separators=(',',':')))
    models={'anthropic':'claude-sonnet-5-5','openai':'gpt-6.1-sol','xai':'grok-4.7'}
    freeze={'files':mapping,'strategy_sha256':strategy,'workflow':'bounded-draft-v1','quote_enablement':False,'no_prompt_retuning_after_input':True,'attempts_allowed':1,'selection_detector':'Desklib only','independent_postselection_detector':'Vanguard original and chosen output; never candidate selection','prospective_gate':{'full_source_review_approved':True,'desklib_output_strictly_below':.3,'desklib_absolute_reduction_at_least':.1},'detector_revisions':{'desklib':DESK_REV,'vanguard':VANG_REV},'created_at':'2026-10-04T00:00:00+00:00','max_new_calls':4,'max_assessments':14,'models':models,'max_estimated_or_reserved_api_usd':.4}
    write(folder/'frozen-protocol.json',freeze)
    source_blocks=[{'id':'title','type':'heading','text':'Title'},{'id':'s1','type':'paragraph','text':'source claim'}]
    output_blocks=[{'id':'title','type':'heading','text':'Title'},{'id':'o1','type':'paragraph','text':'candidate claim'}]
    source='\n\n'.join(b['text'] for b in source_blocks);output='\n\n'.join(b['text'] for b in output_blocks)
    sh,oh=digest(source),digest(output)
    (folder/'source.txt').write_text(source);(folder/'output.txt').write_text(output)
    write(folder/'source-blocks.json',source_blocks)
    write(folder/'source.json',{'text_sha256':sh,'synthetic':True,'blocks':source_blocks,'word_count':3,'authored_at':'2026-10-04T00:01:00+00:00'})
    write(folder/'attempt-started.json',{'source_sha256':sh,'strategy_sha256':strategy,'source_words':3,'at':'2026-10-04T00:03:00+00:00'})
    write(folder/'blind-source-review-input.json',{'original':source_blocks,'candidate':output_blocks,'source_sha256':sh,'candidate_sha256':oh})
    claims=[{'id':f'H{i:02d}','statement':'source claim','source_block':'s1'} for i in range(1,49)]
    inventory={'source_sha256':sh,'created_before_viewing_output':True,'claim_count':48,'claims':claims,'created_at':'2026-10-04T00:02:00+00:00'}
    write(folder/'independent-source-inventory.json',inventory)
    audit={'source_sha256':sh,'candidate_sha256':oh,'sha256':oh,'inventory_file_sha256':digest((folder/'independent-source-inventory.json').read_text()),'reviewer':'independent-agent','reviewed_blind_to_scores':True,'independently_derived_inventory_before_output':True,'claim_count':48,'eligible':True,'verdict':'pass','edits_made':False,'issues':[],'bidirectional_review_complete':True,'title_exactly_preserved':True,'protected_numeric_multiset_preserved':True,'checked_claim_ids':[c['id'] for c in claims], 'whole_source_review':{k:False for k in ('unsupported_additions','qualification_or_uncertainty_loss','causality_changes','quality_issues')},'claim_results':[{'id':c['id'],'status':'preserved','reason':'Compared against source.','source_claim':c['statement'],'source_block':'s1','candidate_block':'o1','candidate_evidence':'candidate claim'} for c in claims],'reverse_candidate_support':[{'candidate_block':'o1','status':'supported','unsupported_claims':[],'supported_by_claim_ids':[c['id'] for c in claims]}],'reviewed_at':'2026-10-04T00:06:00+00:00'}
    write(folder/'independent-final-review.json',audit)
    for label,sha,value in [('original',sh,.21),('output',oh,.16)]:
        score(run,sha,'desklib',value)
        score(run,sha,'vanguard',.35 if label=='original' else .99)
        v=json.loads((run/'scores/vanguard'/(sha+'.json')).read_text());v.update(excluded_from_research_phase_counts=True,purpose='Held-out production E2E evaluation only; never used for selection or retuning',measured_at='2026-10-04T00:05:00+00:00');write(folder/f'vanguard-{label}.json',v)
    before=json.loads((run/'scores/desklib'/(sh+'.json')).read_text())['measurement'];after=json.loads((run/'scores/desklib'/(oh+'.json')).read_text())['measurement']
    usage=[]
    for i,(provider,model) in enumerate(models.items(),1):
        item={'provider':provider,'model':model,'status':'completed','charged_or_reserved_usd':.01,'request_sha256':digest(model+'system'+'prompt'),'input_tokens':1,'output_tokens':1};usage.append(item)
        write(folder/f'{i:03d}-provider_completed.json',{'event':'provider_completed',**item,'system':'system','prompt':'prompt','raw_output':'{}','usage':{'input_tokens':1,'output_tokens':1}})
    report={'writing_method':'bounded-draft-v1','detector_comparison':{'selected_version':'candidate_1','attempts':[{'version':'original','text_sha256':sh,'assessment':before},{'version':'candidate_1','text_sha256':oh,'assessment':after}]},'before_detector':before,'after_detector':after,'provider_usage':usage,'bounded_workflow':{'estimated_or_reserved_usd':.03,'elapsed_seconds':1}}
    result={'blocks':output_blocks,'report':report};write(folder/'result.json',result);write(folder/'018-result.json',{'event':'result','recorded_at':'2026-10-04T00:04:00+00:00',**result})
    return run,code,folder


def test_holdout_binds_exact_text_and_keeps_failed_performance_visible(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    item=holdout_data(run,code)
    assert item['gate_passed'] is False and item['vanguard_worsened'] is True
    assert item['thresholds']=={'30':False,'10':False,'2':False}
    assert item['provider_calls']==3
    assert item['output_sha256']==digest((folder/'output.txt').read_text())


def test_holdout_rejects_changed_frozen_implementation(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    (code/'app/bounded_draft.py').write_text('# changed after freeze\n')
    with pytest.raises(ValueError,match='frozen strategy'):
        holdout_data(run,code)


def test_holdout_rejects_swapped_vanguard_text_identity(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    path=folder/'vanguard-output.json';data=json.loads(path.read_text());data['sha256']='0'*64;write(path,data)
    with pytest.raises(ValueError,match='Score identity'):
        holdout_data(run,code)


def test_holdout_rejects_review_from_different_inventory(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    path=folder/'independent-source-inventory.json';data=json.loads(path.read_text());data['claims'][0]['statement']='different claim';write(path,data)
    with pytest.raises(ValueError,match='review binding'):
        holdout_data(run,code)


def test_holdout_rejects_provider_receipt_with_changed_prompt(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    path=folder/'001-provider_completed.json';data=json.loads(path.read_text());data['prompt']='changed prompt';write(path,data)
    with pytest.raises(ValueError,match='provider usage'):
        holdout_data(run,code)


def test_holdout_rejects_source_authored_before_frozen_strategy(holdout_fixture):
    from scripts.research.private_report import holdout_data
    run,code,folder=holdout_fixture
    path=folder/'source.json';data=json.loads(path.read_text());data['authored_at']='2026-10-03T23:59:00+00:00';write(path,data)
    with pytest.raises(ValueError,match='chronology'):
        holdout_data(run,code)


def test_phase_c_rejects_plan_modified_after_approval(tmp_path):
    from scripts.research.private_report import phase_c_jobs
    plan={'phase':'C','source_sha256':digest('source'),'status':'draft'}
    approval={'authorized':True,'phase':'C','max_new_calls':6,'max_new_distinct':151,'global_budget_usd':1.5,'max_parent_score':.35,'plan_sha256':digest(json.dumps(plan,sort_keys=True))}
    write(tmp_path/'phase-c/plan-draft.json',{**plan,'modified':True})
    write(tmp_path/'phase-c/approval.json',approval)
    write(tmp_path/'phase-c/protocol.json',{**plan,'status':'activated','approval':approval})
    with pytest.raises(ValueError,match='frozen plan'):
        phase_c_jobs(tmp_path,'source',[])
