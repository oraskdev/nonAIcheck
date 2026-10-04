"""Recover frozen omitted proposals with exhaustive review, never new Claude calls."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import random
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r
from scripts.research.phase_b import apply,logit,score_pair
from scripts.research.phase_d import check_text,save_new,known_hashes as previous_hashes

F=r.RUN/'phase-f'
PLAN_SHA='030af446cfe88aafc97e040e319b73040dd31709e16f2a10d3e8b3890a54c9bd'
CAP,MAX_CALLS,OUTPUT_LIMIT,SEED,BEAM=300,2,4500,6100430,3000


def response_json(path,provider):
    record=r.read(path);body=record['body']
    if record['http_status']!=200:raise ValueError('Saved provider response failed')
    if provider=='anthropic':
        if body.get('stop_reason')!='end_turn':raise ValueError('Incomplete cached Claude response')
        text=''.join(c.get('text','') for c in body.get('content',[]) if c.get('type')=='text')
    else:
        if body.get('status')!='completed' or body.get('incomplete_details'):raise ValueError('Incomplete saved Responses output')
        text=''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip()))


def cached_proposals():
    plan=r.read(F/'plan-draft.json');manifest=r.read(F/'cached-proposals.json')
    if r.sha((F/'cached-proposals.json').read_text())!=plan['cached_proposals_sha256']:
        raise ValueError('Cached omitted-proposal manifest changed')
    if manifest['frozen_e_file_sha256']!=plan['frozen_e_file_sha256']:
        raise ValueError('Cached provenance bindings changed')
    for relative,digest in plan['frozen_e_file_sha256'].items():
        if r.sha((r.RUN/relative).read_text())!=digest:raise ValueError('Frozen E evidence changed')
    source,claims=r.bound_source();parent=manifest['parent']
    if (manifest['source_sha256']!=r.sha(source) or parent['sha256']!=r.sha(parent['text']) or
        parent.get('source_sha256')!=r.sha(source) or parent['id']!=plan['parent_id'] or parent['sha256']!=plan['parent_sha256']):
        raise ValueError('Fixed parent/source identity differs')
    r.parent_approvals(parent,r.sha(source),claims)
    if max(score_pair(parent['sha256']))>=.10:raise ValueError('Fixed parent does not meet verified below10 prerequisite')
    reconstructed={}
    for number in (1,2):
        context=r.read(r.RUN/'phase-e/banks'/f'e{number:02d}'/'context.json')
        if context['parent']!=parent:raise ValueError('Cached bank has another parent')
        parsed={}
        for suffix,provider in (('claude','anthropic'),('openai','openai')):
            base=r.RUN/'rounds'/f'phase-e-r{number:02d}-{suffix}'
            request=r.read(str(base)+'.request.json');prompt=json.loads(request['prompt'])
            if (request['provider']!=provider or request['model']!=r.MODELS[provider] or request['max_output_tokens']!=4500 or
                prompt.get('source')!=source or prompt.get('current')!=parent['text'] or prompt.get('claims')!=claims):
                raise ValueError('Cached proposal request source/parent/model differs')
            parsed[suffix]=response_json(str(base)+'.response.json',provider)
            if suffix=='openai' and prompt.get('proposed')!=parsed['claude']:
                raise ValueError('Prior OpenAI request was not supplied the actual cached Claude output')
        cp,op=parsed['claude']['patches'],parsed['openai']['patches']
        if len({p['id'] for p in cp})!=len(cp) or len({p['id'] for p in op})!=len(op):raise ValueError('Duplicate cached proposal IDs')
        returned={p['id'] for p in op}
        for proposal in cp:
            if proposal['id'] in returned:continue
            patch=r.valid_patch(parent['text'],proposal)
            if patch is None:raise ValueError('An omitted proposal fails unchanged local guards')
            key=(patch['find'],patch['replace'])
            reconstructed.setdefault(key,{'patch':patch,'origins':[]})['origins'].append({'bank':number,'original_proposal_id':proposal['id']})
    expected=[]
    for i,item in enumerate(reconstructed.values(),1):
        expected.append({**item['patch'],'id':f'f-p{i:03d}','claude_origins':item['origins']})
    if (len(expected)!=23 or sum(len(p['claude_origins']) for p in expected)!=26 or
        manifest['proposals']!=expected):raise ValueError('Omitted proposal set no longer reconstructs exactly')
    return source,claims,parent,expected


def admitted():
    if not (F/'approval.json').exists():raise RuntimeError('Phase F has not been authorized')
    plan,approval=r.read(F/'plan-draft.json'),r.read(F/'approval.json')
    expected={'authorized':True,'phase':'F','plan_sha256':PLAN_SHA,'max_new_calls':2,'max_new_distinct':300,
              'global_budget_usd':1.5,'max_output_tokens':4500,'new_claude_calls':0}
    if r.sha(json.dumps(plan,sort_keys=True))!=PLAN_SHA or any(approval.get(k)!=v for k,v in expected.items()):
        raise ValueError('Phase F approval or prospective plan changed')
    for relative,digest in plan['frozen_shared_code_sha256'].items():
        if r.sha((r.ROOT/relative).read_text())!=digest:raise ValueError('Frozen shared inference/accounting helper changed')
    if r.cost(r.ledger())>r.LIMIT_USD:raise RuntimeError('Shared global budget already exceeds cap')
    context=cached_proposals()
    if r.sha((F/'prospective-openai-prompt.json').read_text())!=plan['prospective_openai_prompt_sha256']:
        raise ValueError('Prospective exhaustive-review prompt changed')
    source,claims,parent,proposals=context
    prompt=r.read(F/'prospective-openai-prompt.json')
    if (prompt.get('source')!=source or prompt.get('claims')!=claims or prompt.get('current')!=parent['text'] or
        prompt.get('proposals')!=[{k:v for k,v in p.items() if k!='claude_origins'} for p in proposals]):
        raise ValueError('Frozen prompt differs from source/parent/proposal manifest')
    ejobs=[r.read(p) for p in (r.RUN/'phase-e/jobs').glob('*.json')]
    if len(ejobs)!=58 or len({j['sha256'] for j in ejobs})!=58:raise ValueError('Frozen E58 count differs')
    for job in ejobs:
        if job['sha256']!=r.sha(job['text']) or job['source_sha256']!=r.sha(source):raise ValueError('Frozen E text/source differs')
        score_pair(job['sha256'])
    code_hashes={p:r.sha((r.ROOT/p).read_text()) for p in ('scripts/research/phase_f.py','scripts/research/score_phase_f.py')}
    if (F/'protocol.json').exists():
        protocol=r.read(F/'protocol.json')
        if protocol.get('approval')!=approval or protocol.get('runner_sha256')!=code_hashes:
            raise ValueError('Activated Phase F approval or runner changed')
    else:
        save_new(F/'protocol.json',{**plan,'status':'activated','activated_at':r.now(),'approval':approval,'runner_sha256':code_hashes})
    return context


@contextmanager
def locked():
    F.mkdir(parents=True,exist_ok=True)
    with (F/'runner.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def call(provider,prompt,allow_api):
    admitted()
    if provider not in ('openai','xai'):raise ValueError('F permits only OpenAI and Grok requests')
    request_id='phase-f-'+('openai' if provider=='openai' else 'grok')
    existing=r.ledger()['requests']
    if provider=='xai':
        first=existing.get('phase-f-openai',{})
        usage=first.get('usage',{})
        if (first.get('status')!='response_saved' or not isinstance(first.get('actual_usd'),(int,float)) or
            not math.isfinite(first['actual_usd']) or first['actual_usd']<0 or
            not all(isinstance(usage.get(k),int) and usage[k]>=0 for k in ('input_tokens','output_tokens'))):
            raise RuntimeError('Grok requires completed OpenAI actual usage reconciliation')
        receipt=r.read(r.RUN/'rounds/phase-f-openai.response.json')
        if (receipt.get('http_status')!=200 or receipt['body'].get('status')!='completed' or
            receipt['body'].get('incomplete_details') or receipt['body'].get('usage')!=usage or
            abs(first['actual_usd']-(usage['input_tokens']*2+usage['output_tokens']*10)/1e6)>1e-12):
            raise ValueError('First actual usage does not match the saved complete provider receipt')
    if request_id not in existing and sum(k.startswith('phase-f-') for k in existing)>=MAX_CALLS:
        raise RuntimeError('Phase F two-request cap reached')
    paths=[r.RUN/'verified-gate-2.json',*[r.RUN/f'phase-{p}/verified-gate-2.json' for p in ('b','d','e','f')]]
    if any(p.exists() for p in paths):raise RuntimeError('Verified both-below2 already reached')
    return r.call(provider,request_id,r.BASE_SYSTEM,json.dumps(prompt,ensure_ascii=False,separators=(',',':')),
                  allow_api,max_output_tokens=OUTPUT_LIMIT)


def apply_decisions(parent,proposals,answer):
    rows=answer.get('decisions',[])
    if not isinstance(rows,list):raise ValueError('Missing decision list')
    decisions={x.get('id'):x for x in rows}
    expected={p['id'] for p in proposals}
    if len(rows)!=len(expected) or len(decisions)!=len(rows) or set(decisions)!=expected:
        raise ValueError('Exhaustive decision coverage requires every ID exactly once')
    accepted=[]
    for original in proposals:
        row=decisions[original['id']];action=row.get('action');reason=row.get('reason')
        if action not in ('accept','repair','reject') or not isinstance(reason,str) or not reason.strip():
            raise ValueError('Every decision needs an explicit valid action and reason')
        if row.get('find') not in (None,original['find']):raise ValueError('Decision may not change the fixed find span')
        if action=='reject':continue
        replacement=row.get('replace') if action=='repair' else original['replace']
        if action=='accept' and row.get('replace') not in (None,original['replace']):
            raise ValueError('An accepted patch may not silently change replacement')
        patch=r.valid_patch(parent['text'],{'id':original['id'],'find':original['find'],'replace':replacement})
        if patch is None:raise ValueError('A retained repair fails protected span/value/character guards')
        accepted.append(patch)
    return accepted


def review_set(claims,patches,review):
    rows=review.get('patches',[])
    if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
        raise ValueError('Grok patch decisions must be an explicit list of records')
    for row in rows:
        issues=row.get('issues')
        if (not isinstance(row.get('faithful'),bool) or not isinstance(issues,list) or
            not all(isinstance(issue,str) and issue.strip() for issue in issues) or
            (row['faithful'] is False and not issues)):
            raise ValueError('Every Grok decision requires a boolean and explicit rejection issue strings')
    checked={p.get('id'):p for p in rows}
    if (review.get('baseline_faithful') is not True or review.get('baseline_issues') or
        len(review.get('checked_claim_ids',[]))!=32 or set(review['checked_claim_ids'])!={c['id'] for c in claims} or
        len(checked)!=len(rows) or set(checked)!={p['id'] for p in patches}):
        raise ValueError('Complete Grok parent/claim/patch review missing')
    return [p for p in patches if checked[p['id']].get('faithful') is True and not checked[p['id']].get('issues')]


def jobs():
    rows=[r.read(p) for p in sorted((F/'jobs').glob('*.json'))]
    if len(rows)>CAP or len({j['sha256'] for j in rows})!=len(rows):raise ValueError('Phase F cap or uniqueness violated')
    for j in rows:
        if j.get('phase')!='F' or j['sha256']!=r.sha(j['text']):raise ValueError('Phase F text identity differs')
    return rows


def known_hashes():
    return previous_hashes()|{j['sha256'] for j in jobs()}


def review(allow_api=False):
    with locked():
        source,claims,parent,proposals=admitted()
        if (F/'started.json').exists() or jobs():raise RuntimeError('F already started; preserve evidence without implicit restart')
        save_new(F/'started.json',{'at':r.now(),'parent_sha256':parent['sha256'],'fixed_proposals':len(proposals)})
        decisions=call('openai',r.read(F/'prospective-openai-prompt.json'),allow_api)
        save_new(F/'openai-decisions.json',decisions)
        accepted=apply_decisions(parent,proposals,decisions)
        save_new(F/'retained-before-grok.json',{'patches':accepted,'all_proposals_decided':len(proposals)})
        if not accepted:
            save_new(F/'no-retained-proposals.json',{'at':r.now(),'new_unique':0,'grok_called':False,'reason':'All proposals explicitly rejected'})
            print('No retained proposal; no second provider request');r.archive();return
        prompt={'source':source,'claims':claims,'current':parent['text'],'patches':accepted,
                'task':'Review the COMPLETE parent against ORIGINAL and ALL32 claims, then every retained patch independently applied to it. Return exactly one row for EVERY patch ID, no missing/extra/duplicate IDs. Reject missing or added claims, altered uncertainty, timing, conditions, causal relationships or serious prose defects; accept faithful ordinary rephrasing. Return {baseline_faithful:boolean,baseline_issues:[string],checked_claim_ids:[all32IDs],patches:[{id,faithful:boolean,issues:[string]}]}. Do not rewrite patches.'}
        verdict=call('xai',prompt,allow_api)
        save_new(F/'grok-review.json',verdict)
        approved=review_set(claims,accepted,verdict)
        save_new(F/'bank.json',{'parent':parent,'patches':approved,'source_sha256':r.sha(source)})
        paths=[F/'bank.json',F/'openai-decisions.json',F/'retained-before-grok.json',F/'grok-review.json',
               *[r.RUN/'rounds'/f'phase-f-{p}.{s}.json' for p in ('openai','grok') for s in ('request','response')]]
        save_new(F/'bindings.json',{str(p.relative_to(r.RUN)):r.sha(p.read_text()) for p in paths})
        seen=known_hashes();before=set(seen);queued={};singles=[];made=[]
        for p in approved:
            text=check_text(apply(parent['text'],[p]),source);digest=r.sha(text)
            row={'patch_id':p['id'],'sha256':digest,'new_unique':digest not in seen}
            if digest not in seen:
                cid=f'f01-s{len(made)+1:03d}'
                save_new(F/'jobs'/(cid+'.json'),{'id':cid,'phase':'F','text':text,'sha256':digest,'source_sha256':r.sha(source),
                    'parent_id':parent['id'],'parent_sha256':parent['sha256'],'patch_ids':[p['id']],'created_at':r.now(),
                    'combined_full_source_review':'pending','individual_patches_reviewed':True})
                seen.add(digest);queued[digest]=cid;made.append(cid);row['job_id']=cid
            elif digest in before:score_pair(digest)
            else:row.update({'job_id':queued[digest],'same_bank_duplicate':True})
            singles.append(row)
        save_new(F/'singles.json',{'at':r.now(),'new_unique':len(made),'candidate_ids':made,'singles':singles,'approved_patches':len(approved)})
        print('Phase F saved',len(made),'new singles from',len(approved),'approved cached proposals',flush=True);r.archive()


def bound_bank():
    source,claims,parent,proposals=admitted()
    for relative,digest in r.read(F/'bindings.json').items():
        if r.sha((r.RUN/relative).read_text())!=digest:raise ValueError('Frozen F bank/request/response changed')
    op=response_json(r.RUN/'rounds/phase-f-openai.response.json','openai')
    if op!=r.read(F/'openai-decisions.json'):raise ValueError('OpenAI decisions differ from saved actual response')
    req=r.read(r.RUN/'rounds/phase-f-openai.request.json')
    if req['provider']!='openai' or req['model']!=r.MODELS['openai'] or req['max_output_tokens']!=4500 or json.loads(req['prompt'])!=r.read(F/'prospective-openai-prompt.json'):
        raise ValueError('OpenAI request differs from frozen proposal review')
    retained=apply_decisions(parent,proposals,op)
    if retained!=r.read(F/'retained-before-grok.json')['patches']:raise ValueError('Retained decisions changed')
    req=r.read(r.RUN/'rounds/phase-f-grok.request.json');prompt=json.loads(req['prompt'])
    if (req['provider']!='xai' or req['model']!=r.MODELS['xai'] or req['max_output_tokens']!=4500 or
        prompt.get('source')!=source or prompt.get('claims')!=claims or prompt.get('current')!=parent['text'] or prompt.get('patches')!=retained):
        raise ValueError('Grok request differs from exact retained patches or source')
    verdict=response_json(r.RUN/'rounds/phase-f-grok.response.json','xai')
    if verdict!=r.read(F/'grok-review.json'):raise ValueError('Grok review differs from saved actual response')
    approved=review_set(claims,retained,verdict);bank=r.read(F/'bank.json')
    if bank!={'parent':parent,'patches':approved,'source_sha256':r.sha(source)}:raise ValueError('Approved bank differs from exact reviewed patches')
    return bank


def ranked(bank):
    parent,patches=bank['parent'],bank['patches'];base=list(map(logit,score_pair(parent['sha256'])))
    deltas=[[logit(x)-b for x,b in zip(score_pair(r.sha(apply(parent['text'],[p]))),base)] for p in patches]
    states=[((),tuple(base))];result=[]
    for width in range(1,9):
        expanded=[]
        for indices,values in states:
            for i in range(indices[-1]+1 if indices else 0,len(patches)):
                p=patches[i]
                if any(not(p['end']<=patches[j]['start'] or p['start']>=patches[j]['end']) for j in indices):continue
                expanded.append((indices+(i,),tuple(x+y for x,y in zip(values,deltas[i]))))
        expanded.sort(key=lambda x:(max(x[1]),sum(x[1]),x[0]));states=expanded[:BEAM]
        if width>=2:result.extend(states)
    return sorted(result,key=lambda x:(max(x[1]),sum(x[1]),x[0]))


def combine():
    with locked():
        source,_,_,_=admitted()
        if (F/'complete.json').exists() or any((F/'jobs').glob('f01-c*.json')):raise RuntimeError('F combinations already started; no overwrite')
        bank=bound_bank();maximum=CAP-len(jobs())
        if maximum<=0:raise RuntimeError('No remaining F distinct-text capacity')
        candidates=[];seen=known_hashes()
        for indices,predicted in ranked(bank):
            patches=[bank['patches'][i] for i in indices];text=check_text(apply(bank['parent']['text'],patches),source);digest=r.sha(text)
            if digest in seen:continue
            seen.add(digest);candidates.append({'text':text,'sha256':digest,'patch_ids':[p['id'] for p in patches],
                                               'ranking_only_predicted_logits':predicted,'prediction_is_not_a_measurement':True})
        count=math.floor(maximum*.8);selected=candidates[:count];rest=candidates[count:]
        random.Random(SEED).shuffle(rest);selected+=rest[:maximum-len(selected)];made=[]
        for row in selected:
            cid=f'f01-c{len(made)+1:03d}'
            save_new(F/'jobs'/(cid+'.json'),{**row,'id':cid,'phase':'F','source_sha256':r.sha(source),
                'parent_id':bank['parent']['id'],'parent_sha256':bank['parent']['sha256'],'created_at':r.now(),
                'combined_full_source_review':'pending','individual_patches_reviewed':True});made.append(cid)
        save_new(F/'complete.json',{'at':r.now(),'unique_generated':len(jobs()),'new_combinations':len(made),
                                  'candidate_ids':made,'ranked_unused_pool':len(candidates),'scoring':'pending'})
        print('Phase F generated',len(made),'new combinations; exact measurements pending',flush=True);r.archive()


def status():
    source,claims=r.bound_source();all_jobs=jobs();rows=[]
    for job in all_jobs:
        if job.get('source_sha256')!=r.sha(source):raise ValueError('F job source differs')
        try:d,v=score_pair(job['sha256'])
        except FileNotFoundError:continue
        try:reviewers=r.parent_approvals(job,r.sha(source),claims)
        except ValueError:reviewers=[]
        rows.append({'id':job['id'],'sha256':job['sha256'],'desklib':d,'vanguard':v,'maximum':max(d,v),
                     'source_reviewers':reviewers,'review':'source_verified' if reviewers else 'pending'})
    rows.sort(key=lambda x:(x['maximum'],x['desklib']+x['vanguard'],x['id']))
    result={'at':r.now(),'phase':'F','unique_generated':len(all_jobs),'paired':len(rows),
            'new_provider_requests_attempted':sum(k.startswith('phase-f-') for k in r.ledger()['requests']),
            'global_estimated_or_reserved_api_usd':r.cost(r.ledger()),'best':rows[:20],'scores':rows,
            'selected_verified':next((x for x in rows if x['review']=='source_verified'),None)}
    for label,threshold in ((30,.30),(10,.10),(2,.02)):
        eligible=[x for x in rows if x['maximum']<threshold and x['review']=='source_verified']
        result[f'verified_below_both_{label}']=len(eligible);gate=F/f'verified-gate-{label}.json'
        if eligible and not gate.exists():
            selected=eligible[0]
            save_new(gate,{'at':r.now(),'phase':'F','threshold':threshold,'selected':selected,
                'job':r.read(F/'jobs'/(selected['id']+'.json')),
                'measurements':{d:r.read(r.RUN/'scores'/d/(selected['sha256']+'.json')) for d in ('desklib','vanguard')},
                'scope':'One-source adaptive in-sample result; not general detector/watermark or held-out evidence.'})
    r.save(F/'status.json',result);print(json.dumps({k:v for k,v in result.items() if k!='scores'},indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['review','combine','status']);p.add_argument('--allow-api',action='store_true');a=p.parse_args()
    if a.action=='review':review(a.allow_api)
    else:globals()[a.action]()
