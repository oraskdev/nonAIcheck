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


@pytest.fixture
def phase_d_fixture(tmp_path, monkeypatch):
    from scripts.research import private_report as report
    from scripts.research.recovery import valid_patch
    from scripts.research.phase_b import logit
    source='Fixture title\n\nThe room gets bright light in the morning. The door stays closed during the afternoon.'
    claims=[{'id':f'G{i:02d}','text':'Synthetic source claim.'} for i in range(1,33)]
    parent={'id':'p1','phase':'B','text':source,'sha256':digest(source),'source_sha256':digest(source)}
    plan={'phase':'D','status':'draft','source_sha256':digest(source),'initial_parent_id':'p1','initial_parent_sha256':parent['sha256']}
    plan_hash=digest(json.dumps(plan,sort_keys=True));monkeypatch.setattr(report,'PHASE_D_PLAN_SHA',plan_hash)
    approval={'authorized':True,'phase':'D','plan_sha256':plan_hash,'max_banks':3,'max_new_calls':9,'max_new_distinct':450,'per_bank_max':150,'global_budget_usd':1.5}
    folder=tmp_path/'phase-d/banks/d01'
    for name,data in [('plan-draft',plan),('approval',approval),('protocol',{**plan,'status':'activated','plan_sha256':plan_hash,'approval':approval})]:
        write(tmp_path/f'phase-d/{name}.json',data)
    proposed={'patches':[{'id':'p01','find':'The room gets bright light in the morning.','replace':'Bright light fills the room in the morning.'},{'id':'p02','find':'The door stays closed during the afternoon.','replace':'During the afternoon, the door stays closed.'}]}
    patches=[valid_patch(source,p) for p in proposed['patches']]
    assert all(patches)
    approved={'baseline_faithful':True,'baseline_issues':[],'checked_claim_ids':[c['id'] for c in claims],'patches':[{'id':p['id'],'faithful':True,'issues':[]} for p in patches]}
    context={'bank':1,'parent':parent,'parent_exact_scores':[.2,.2],'parent_source_reviewers':['one','two'],'source_sha256':digest(source),'at':'2026-10-04T00:00:00+00:00'}
    write(folder/'context.json',context);write(folder/'review.json',approved);write(folder/'bank.json',{'parent':parent,'source_sha256':digest(source),'patches':patches})
    requests={}
    for suffix,provider,model,out in [('claude','anthropic','claude-sonnet-5-5',proposed),('openai','openai','gpt-6.1-sol',proposed),('grok','xai','grok-4.7',approved)]:
        prompt={'source':source,'claims':claims,'current':source}
        if suffix=='openai':prompt['proposed']=proposed
        if suffix=='grok':prompt['patches']=patches
        request={'provider':provider,'model':model,'system':'Fixture system.','prompt':json.dumps(prompt),'max_output_tokens':100,'reasoning':'low'}
        request_id='phase-d-r01-'+suffix
        write(tmp_path/f'rounds/{request_id}.request.json',request)
        body={'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps(out)}]} if suffix=='claude' else {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(out)}]}]}
        write(tmp_path/f'rounds/{request_id}.response.json',{'http_status':200,'body':body})
        requests[request_id]={'fingerprint':digest(json.dumps(request,sort_keys=True)),'started_at':'2026-10-04T00:01:00+00:00','reserved_usd':.1,'actual_usd':.01,'status':'response_saved'}
    write(tmp_path/'ledger.json',{'limit_usd':1.5,'requests':requests})
    for who in ['one','two']:write(tmp_path/f'reviews/parent-{who}.json',review(parent['sha256'],digest(source),who))
    for detector in ['desklib','vanguard']:score(tmp_path,parent['sha256'],detector,.2)
    singles=[];jobs=[]
    for i,patch in enumerate(patches,1):
        text=source[:patch['start']]+patch['replace']+source[patch['end']:]
        job={'id':f'd01-s{i:03d}','phase':'D','bank':1,'source_sha256':digest(source),'parent_id':'p1','parent_sha256':parent['sha256'],'patch_ids':[patch['id']],'text':text,'sha256':digest(text)}
        jobs.append(job);write(tmp_path/f'phase-d/jobs/{job["id"]}.json',job)
        singles.append({'patch_id':patch['id'],'sha256':job['sha256'],'job_id':job['id'],'new_unique':True})
        for detector in ['desklib','vanguard']:score(tmp_path,job['sha256'],detector,.1)
    write(folder/'singles.json',{'bank':1,'new_unique':2,'candidate_ids':[j['id'] for j in jobs],'singles':singles})
    combined=source
    for patch in reversed(patches):combined=combined[:patch['start']]+patch['replace']+combined[patch['end']:]
    combination={'id':'d01-c001','phase':'D','bank':1,'source_sha256':digest(source),'parent_id':'p1','parent_sha256':parent['sha256'],'patch_ids':[p['id'] for p in patches],'text':combined,'sha256':digest(combined),'ranking_only_predicted_logits':[2*logit(.1)-logit(.2)]*2,'prediction_is_not_a_measurement':True}
    jobs.append(combination);write(tmp_path/'phase-d/jobs/d01-c001.json',combination)
    names=[f'phase-d/banks/d01/{n}.json' for n in ['context','review','bank']]+[f'rounds/phase-d-r01-grok.{n}.json' for n in ['request','response']]
    write(folder/'bindings.json',{n:digest((tmp_path/n).read_text()) for n in names})
    return tmp_path,source,claims,[parent],jobs


def test_phase_d_predictions_are_not_measurements(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs, load_pair
    run,source,claims,previous,jobs=phase_d_fixture
    assert phase_d_jobs(run,source,claims,previous)==sorted(jobs,key=lambda j:j['id'])
    assert load_pair(run,jobs[-1]['sha256']) is None


def test_phase_d_rejects_changed_context_and_changed_raw_approval(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs
    run,source,claims,previous,jobs=phase_d_fixture
    folder=run/'phase-d/banks/d01';path=folder/'review.json';item=json.loads(path.read_text());item['baseline_issues']=['Invented claim'];write(path,item)
    with pytest.raises(ValueError,match='frozen context/bank/provider'):
        phase_d_jobs(run,source,claims,previous)
    path=folder/'bindings.json';binding=json.loads(path.read_text());binding['phase-d/banks/d01/review.json']=digest((folder/'review.json').read_text());write(path,binding)
    with pytest.raises(ValueError,match='raw response'):
        phase_d_jobs(run,source,claims,previous)


def test_phase_d_rejects_rehashed_text_outside_approved_patches(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs
    run,source,claims,previous,jobs=phase_d_fixture
    job={**jobs[-1],'text':jobs[-1]['text']+' Extra content.'};job['sha256']=digest(job['text']);write(run/'phase-d/jobs/d01-c001.json',job)
    with pytest.raises(ValueError,match='reconstruction'):
        phase_d_jobs(run,source,claims,previous)


def test_phase_d_rejects_prediction_without_measured_inputs(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs
    run,source,claims,previous,jobs=phase_d_fixture
    (run/'scores/vanguard'/(jobs[0]['sha256']+'.json')).unlink()
    with pytest.raises(ValueError,match='paired single-patch'):
        phase_d_jobs(run,source,claims,previous)


def test_phase_d_rejects_changed_ranking_prediction(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs
    run,source,claims,previous,jobs=phase_d_fixture
    job={**jobs[-1],'ranking_only_predicted_logits':[-100,-100]};write(run/'phase-d/jobs/d01-c001.json',job)
    with pytest.raises(ValueError,match='rank-only predictions'):
        phase_d_jobs(run,source,claims,previous)


def test_phase_d_rejects_previously_counted_hash(phase_d_fixture):
    from scripts.research.private_report import phase_d_jobs
    run,source,claims,previous,jobs=phase_d_fixture
    with pytest.raises(ValueError,match='previously counted'):
        phase_d_jobs(run,source,claims,previous+[{**jobs[-1],'id':'old-phase-a','phase':'A'}])


@pytest.fixture
def phase_e_fixture(phase_d_fixture,monkeypatch):
    from scripts.research import private_report as report
    run,source,claims,previous,_=phase_d_fixture
    # Use synthetic D evidence to exercise the common bank schema under E's own scope.
    for old in list(run.rglob('*.json')):
        name=str(old.relative_to(run)).replace('phase-d','phase-e').replace('d01','e01')
        content=old.read_text().replace('phase-d','phase-e').replace('d01','e01').replace('"phase": "D"','"phase": "E"')
        (run/name).parent.mkdir(parents=True,exist_ok=True);(run/name).write_text(content)
    plan=json.loads((run/'phase-e/plan-draft.json').read_text())
    plan.pop('initial_parent_id');plan.pop('initial_parent_sha256')
    plan_hash=digest(json.dumps(plan,sort_keys=True));monkeypatch.setattr(report,'PHASE_E_PLAN_SHA',plan_hash)
    approval={'authorized':True,'phase':'E','plan_sha256':plan_hash,'max_banks':2,'max_new_calls':6,'max_new_distinct':300,'per_bank_max':150,'global_budget_usd':1.5,'max_output_tokens':4500,'patch_range':[14,18]}
    write(run/'phase-e/plan-draft.json',plan);write(run/'phase-e/approval.json',approval);write(run/'phase-e/protocol.json',{**plan,'status':'activated','plan_sha256':plan_hash,'approval':approval})
    ledger=json.loads((run/'ledger.json').read_text())
    for name in ['claude','openai','grok']:
        path=run/f'rounds/phase-e-r01-{name}.request.json';request=json.loads(path.read_text());request['max_output_tokens']=4500;write(path,request)
        ledger['requests'][f'phase-e-r01-{name}']['fingerprint']=digest(json.dumps(request,sort_keys=True))
    write(run/'ledger.json',ledger)
    path=run/'phase-e/banks/e01/bindings.json';binding=json.loads(path.read_text());write(path,{name:digest((run/name).read_text()) for name in binding})
    return run,source,claims,previous


def test_phase_e_uses_own_scope_without_requiring_d_initial_parent(phase_e_fixture):
    from scripts.research.private_report import patch_phase_jobs
    run,source,claims,previous=phase_e_fixture
    jobs=patch_phase_jobs(run,source,claims,previous,'E')
    assert len(jobs)==3 and all(j['phase']=='E' for j in jobs)


def test_phase_e_rejects_overlarge_response_cap_even_with_rebound_request(phase_e_fixture):
    from scripts.research.private_report import patch_phase_jobs
    run,source,claims,previous=phase_e_fixture
    path=run/'rounds/phase-e-r01-openai.request.json';request=json.loads(path.read_text());request['max_output_tokens']=8000;write(path,request)
    path=run/'ledger.json';ledger=json.loads(path.read_text());ledger['requests']['phase-e-r01-openai']['fingerprint']=digest(json.dumps(request,sort_keys=True));write(path,ledger)
    with pytest.raises(ValueError,match='Phase E provider request/response'):
        patch_phase_jobs(run,source,claims,previous,'E')


def test_phase_e_rejects_new_text_marked_as_reuse(phase_e_fixture):
    from scripts.research.private_report import patch_phase_jobs
    run,source,claims,previous=phase_e_fixture
    path=run/'phase-e/banks/e01/singles.json';manifest=json.loads(path.read_text());manifest['singles'][0]['new_unique']=False;write(path,manifest)
    with pytest.raises(ValueError,match='queued single-patch identity'):
        patch_phase_jobs(run,source,claims,previous,'E')


def test_phase_e_rejects_more_than_18_refined_patches(phase_e_fixture):
    from scripts.research.private_report import patch_phase_jobs
    from scripts.research.recovery import valid_patch
    run,source,claims,previous=phase_e_fixture
    response_path=run/'rounds/phase-e-r01-openai.response.json';receipt=json.loads(response_path.read_text())
    result=json.loads(receipt['body']['output'][0]['content'][0]['text'])
    result['patches'] += [{**result['patches'][0],'id':f'p{i:02d}'} for i in range(3,20)]
    receipt['body']['output'][0]['content'][0]['text']=json.dumps(result);write(response_path,receipt)
    path=run/'rounds/phase-e-r01-grok.request.json';request=json.loads(path.read_text());prompt=json.loads(request['prompt']);prompt['patches']=[valid_patch(source,p) for p in result['patches']];request['prompt']=json.dumps(prompt);write(path,request)
    path=run/'ledger.json';ledger=json.loads(path.read_text());ledger['requests']['phase-e-r01-grok']['fingerprint']=digest(json.dumps(request,sort_keys=True));write(path,ledger)
    path=run/'phase-e/banks/e01/bindings.json';binding=json.loads(path.read_text());write(path,{name:digest((run/name).read_text()) for name in binding})
    with pytest.raises(ValueError,match='reviewer did not receive the exact validated refined patches'):
        patch_phase_jobs(run,source,claims,previous,'E')


@pytest.fixture
def phase_e_prerequisites_fixture(tmp_path,monkeypatch):
    from scripts.research import private_report as report
    root=tmp_path/'code';run=tmp_path/'run';source='Synthetic prerequisite source.';sh=digest(source)
    helpers={}
    for name in report.FROZEN_RESEARCH_HELPERS:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# Frozen test helper\n');helpers[name]=digest(path.read_text())
    monkeypatch.setattr(report,'ROOT',root)
    claims=[{'id':f'G{i:02d}','text':'Synthetic claim.'} for i in range(1,33)]
    jobs=[]
    for i in range(450):
        text=f'Synthetic measured D candidate {i}.';job={'id':f'd{i:03d}','phase':'D','text':text,'sha256':digest(text),'source_sha256':sh};jobs.append(job)
        for detector in ['desklib','vanguard']:score(run,job['sha256'],detector,.08)
    for who in ['first','second']:write(run/f'reviews/gate-{who}.json',review(jobs[0]['sha256'],sh,who))
    gate={'phase':'D','threshold':.1,'job':jobs[0],'measurements':report.load_pair(run,jobs[0]['sha256']),'selected':{'sha256':jobs[0]['sha256']}}
    path=run/'phase-d/verified-gate-10.json';write(path,gate)
    plan={'frozen_shared_code_sha256':helpers,'first_verified_d_below10_checkpoint_sha256':digest(path.read_text())}
    write(run/'phase-e/plan-draft.json',plan);monkeypatch.setattr(report,'PHASE_E_PLAN_SHA',digest(json.dumps(plan,sort_keys=True)))
    return run,source,claims,jobs,root


def test_phase_e_requires_complete_450_and_immutable_helpers(phase_e_prerequisites_fixture):
    from scripts.research.private_report import phase_e_prerequisites
    run,source,claims,jobs,root=phase_e_prerequisites_fixture
    phase_e_prerequisites(run,source,claims,jobs)
    with pytest.raises(ValueError,match='450 distinct'):
        phase_e_prerequisites(run,source,claims,jobs[:-1])
    (root/'scripts/research/recovery.py').write_text('# Changed helper\n')
    with pytest.raises(ValueError,match='frozen shared helper'):
        phase_e_prerequisites(run,source,claims,jobs)


def test_phase_e_requires_exact_checkpoint_pair_and_two_current_approvals(phase_e_prerequisites_fixture):
    from scripts.research.private_report import phase_e_prerequisites
    run,source,claims,jobs,root=phase_e_prerequisites_fixture
    (run/'reviews/gate-second.json').unlink()
    with pytest.raises(ValueError,match='two reviews'):
        phase_e_prerequisites(run,source,claims,jobs)


def test_phase_g_integration_keeps_provisional_predictions_out_of_selection(study,monkeypatch):
    import sys
    from types import SimpleNamespace
    source_hash=digest((study/'source.txt').read_text())
    baseline=json.loads((study/'baseline.json').read_text())
    jobs=[]
    for i,(text,values,approved) in enumerate([('Reviewed phase G draft.',(.05,.06),True),('Unaudited phase G draft.',(.001,.001),False)],1):
        job={'id':f'g01-c{i:04d}','phase':'G','text':text,'sha256':digest(text),'source_sha256':source_hash,'parent_id':baseline['id'],'parent_sha256':baseline['sha256'],'ranking_only_predicted_logits':[-100,-100],'prediction_is_not_a_measurement':True}
        jobs.append(job)
        for detector,value in zip(('desklib','vanguard'),values):score(study,job['sha256'],detector,value)
        if approved:
            for who in ['g-first','g-second']:write(study/f'reviews/{who}.json',review(job['sha256'],source_hash,who))
    (study/'phase-g').mkdir()
    # The isolated helper owns provenance validation; exercise main's independent measurement/review gate.
    monkeypatch.setitem(sys.modules,'scripts.research.private_report_g',SimpleNamespace(phase_g_data=lambda *args:{'jobs':jobs,'state':'measuring','new_provider_requests':0,'completed_patch_banks':0}))
    result=build_data(study)
    assert result['selected']['job']['id']=='g01-c0001'
    assert result['selected']['scores']=={'desklib':.05,'vanguard':.06}
    assert result['thresholds']=={'30':True,'10':True,'2':False}
    assert result['phase_counts'][-1]=={'phase':'G','unique':2,'paired':2,'reviewed':1,'new_provider_requests':0,'verified_thresholds':{'30':True,'10':True,'2':False}}
    assert 'zero provider requests' in render(result)
