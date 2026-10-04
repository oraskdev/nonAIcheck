"""Final bounded adaptive research phase; separate coordinator authorization required.

Single-patch exact measurements rank combinations; predictions never replace
measurements. The shared ledger and immutable request IDs enforce the global cap.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import random
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r
from scripts.research.phase_b import apply, logit, score_pair

D = r.RUN / 'phase-d'
MAX_BANKS, MAX_CALLS, MAX_TEXTS, PER_BANK = 3, 9, 450, 150
BEAM, SEED = 2000, 6100410
PHASE, ID_PREFIX, REQUEST_PREFIX = 'D', 'd', 'phase-d-'
OUTPUT_LIMIT, PATCH_MIN, PATCH_MAX = r.MAX_OUTPUT, 18, 24
EXTRA_APPROVAL_FIELDS = {}
PARENT_PHASES = ('A', 'B', 'D')

PLAN_SHA = '1c4581294ad31e3b6fcd8f15cbeee6e4482e233d1417ac3c854ef889cf2d9df8'


def admitted():
    if not (D/'approval.json').exists():
        raise RuntimeError('Phase D has not been authorized')
    plan, approval = r.read(D/'plan-draft.json'), r.read(D/'approval.json')
    expected = {'authorized':True, 'phase':PHASE, 'plan_sha256':PLAN_SHA,
                'max_banks':MAX_BANKS, 'max_new_calls':MAX_CALLS,
                'max_new_distinct':MAX_TEXTS, 'per_bank_max':PER_BANK,
                'global_budget_usd':r.LIMIT_USD, **EXTRA_APPROVAL_FIELDS}
    if r.sha(json.dumps(plan, sort_keys=True)) != PLAN_SHA or any(approval.get(k) != v for k,v in expected.items()):
        raise ValueError('Phase D approval or prospective plan differs from frozen scope')
    if r.cost(r.ledger()) > r.LIMIT_USD:
        raise RuntimeError('Global research budget exceeds limit')
    source, claims = r.bound_source()
    if plan.get('source_sha256') != r.sha(source):
        raise ValueError('Phase D source changed')
    path = D/'protocol.json'
    if path.exists():
        protocol = r.read(path)
        if protocol.get('approval') != approval or protocol.get('plan_sha256') != PLAN_SHA:
            raise ValueError('Activated Phase D approval changed')
    else:
        r.save(path, {**plan, 'status':'activated', 'activated_at':r.now(),
                      'plan_sha256':PLAN_SHA, 'approval':approval})
    return source, claims


@contextmanager
def coordinator_lock():
    D.mkdir(parents=True, exist_ok=True)
    with (D/'runner.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def save_new(path, value):
    if path.exists():
        raise RuntimeError('Refusing to overwrite Phase D evidence: '+path.name)
    r.save(path, value)


def jobs():
    result = [r.read(p) for p in sorted((D/'jobs').glob('*.json'))]
    if len(result) > MAX_TEXTS or len({j['sha256'] for j in result}) != len(result):
        raise ValueError('Phase D distinct-text count or uniqueness violated')
    for j in result:
        if j.get('phase') != PHASE or j['sha256'] != r.sha(j['text']):
            raise ValueError('Phase D text identity differs')
    return result


def known_hashes():
    source, _ = r.bound_source()
    seen = {r.sha(source)}
    for path in (r.RUN/'baseline.json', r.RUN/'source-original.json'):
        if path.exists(): seen.add(r.read(path)['sha256'])
    for directory in (r.RUN/'jobs', r.RUN/'phase-b/jobs', r.RUN/'phase-c/jobs', r.RUN/'phase-d/jobs', r.RUN/'phase-e/jobs'):
        for path in directory.glob('*.json'): seen.add(r.read(path)['sha256'])
    for path in (r.RUN/'rounds').glob('*-bank.json'):
        seen.add(r.read(path)['parent']['sha256'])
    if (r.RUN/'phase-c/bank.json').exists(): seen.add(r.read(r.RUN/'phase-c/bank.json')['parent']['sha256'])
    for phase in ('D','E'):
        for path in (r.RUN/('phase-'+phase.lower())/'banks').glob('*/context.json'): seen.add(r.read(path)['parent']['sha256'])
    historical = r.read(r.ROOT/'static/research-ten-trials.json')
    for row in [historical['original'],historical['baseline'],historical['selected'],*historical['trials'],*historical['repairs']]:
        if row.get('sha256'): seen.add(row['sha256'])
    return seen


def check_text(text, source):
    if (not isinstance(text,str) or not text.strip() or r.numbers(text) != r.numbers(source) or
        not r.clean(text) or text.split('\n')[0] != source.split('\n')[0] or text.count(source.split('\n')[0]) != 1):
        raise ValueError('Candidate changed title/numbers or contains hidden/control characters')
    return text


def best_parent():
    source, claims = r.bound_source()
    choices = []
    for phase in PARENT_PHASES:
        directory = r.RUN/'jobs' if phase=='A' else r.RUN/('phase-'+phase.lower())/'jobs'
        for path in directory.glob('*.json'):
            job = r.read(path)
            if job.get('source_sha256') != r.sha(source) or job.get('sha256') != r.sha(job['text']):
                raise ValueError('Candidate source/text binding differs')
            try:
                reviewers = r.parent_approvals(job,r.sha(source),claims)
                pair = score_pair(job['sha256'])
            except (FileNotFoundError, ValueError):
                continue
            choices.append((max(pair),sum(pair),job['id'],job,pair,reviewers))
    if not choices: raise RuntimeError('No twice-reviewed exact-measured A/B/D parent')
    return min(choices,key=lambda x:x[:3])


def call(provider, number, prompt, allow_api):
    admitted()
    if provider not in ('anthropic','openai','xai') or not 1 <= number <= MAX_BANKS:
        raise ValueError('Unknown Phase D provider or bank')
    suffix = {'anthropic':'claude','openai':'openai','xai':'grok'}[provider]
    request_id = f'{REQUEST_PREFIX}r{number:02d}-{suffix}'
    existing = r.ledger()['requests']
    count = sum(k.startswith(REQUEST_PREFIX) for k in existing)
    if request_id not in existing and count >= MAX_CALLS:
        raise RuntimeError('Phase D nine-request cap reached')
    if any(path.exists() for path in (r.RUN/'verified-gate-2.json', r.RUN/'phase-b/verified-gate-2.json', r.RUN/'phase-d/verified-gate-2.json', r.RUN/'phase-e/verified-gate-2.json')):
        raise RuntimeError('Both-below2 checkpoint reached; no further Phase D paid calls')
    return r.call(provider,request_id,r.BASE_SYSTEM,json.dumps(prompt,ensure_ascii=False),allow_api,max_output_tokens=OUTPUT_LIMIT)


def generate_bank(number, allow_api=False):
    with coordinator_lock():
        source, claims = admitted()
        if not 1 <= number <= MAX_BANKS: raise ValueError('At most three Phase D banks')
        folder = D/'banks'/f'{ID_PREFIX}{number:02d}'
        if folder.exists(): raise RuntimeError('Bank already started; preserve partial or completed evidence without implicit retry')
        if number > 1 and not (D/'banks'/f'{ID_PREFIX}{number-1:02d}'/'complete.json').exists():
            raise RuntimeError('Previous bank combination generation must be complete')
        if len(jobs()) >= MAX_TEXTS: raise RuntimeError('Phase D distinct-text cap reached before provider calls')
        maximum, _, _, parent, pair, reviewers = best_parent()
        plan = r.read(D/'plan-draft.json')
        if number == 1 and plan.get('initial_parent_id') and (parent['id'] != plan['initial_parent_id'] or parent['sha256'] != plan['initial_parent_sha256']):
            raise ValueError('First Phase D parent differs from prospective initial parent')
        if maximum < .02: raise RuntimeError('Both-below2 reviewed target already reached')
        bstatus = r.read(r.RUN/'phase-b/status.json')
        context = {'at':r.now(),'bank':number,'parent':parent,'parent_exact_scores':pair,
                   'parent_source_reviewers':reviewers,'source_sha256':r.sha(source),
                   'interim_b_paired':bstatus['paired'],'interim_b_generated':bstatus['unique_generated'],
                   'selection':'Lowest maximum exact score among currently twice-source-reviewed A/B/D candidates'}
        save_new(folder/'context.json',context)
        provider_context = {'source':source,'claims':claims,'current':parent['text']}
        proposed = call('anthropic',number,{**provider_context,
            'task':f'Propose{PATCH_MIN}–{PATCH_MAX} faithful everyday sentence alternatives for this personal note. Focus on concrete direct language, natural variations in clause order and sentence length, without adding anecdotes, personality, new claims, filler or deliberate errors. Cover different parts of the note. Each find is an exact unique20–450character span on one paragraph, replacement15–600characters without newlines. Alternatives may overlap but overlapping alternatives will not be combined. Preserve every condition, uncertainty, causal relationship and timing; exact title, numeric literals and local may/might/should/would/could/must unchanged. Return {{patches:[{{id,find,replace,reason}}]}}.'},allow_api)
        refined = call('openai',number,{**provider_context,'proposed':proposed,
            'task':f'Refine the proposed{PATCH_MIN}–{PATCH_MAX} alternatives against ORIGINAL and all32 claims. Make source-fidelity repairs, but preserve correct natural sentence variation and do not normalize it into a standard essay. Reject added advice/facts, shifted uncertainty/conditions/causality, manufactured disfluency or awkward prose. Exact unique find20–450characters and replacement15–600characters; no newlines; title/numbers/local modal words unchanged. Return {{patches:[{{id,find,replace,reason}}]}}.'},allow_api)
        patches=[]
        for item in refined.get('patches',[]):
            if not isinstance(item.get('id'),str) or any(p['id']==item['id'] for p in patches): continue
            patch=r.valid_patch(parent['text'],item)
            if patch: patches.append(patch)
        if len(patches)>PATCH_MAX: raise ValueError('Provider exceeded24 accepted proposal slots')
        review = call('xai',number,{**provider_context,'patches':patches,
            'task':'Compare the COMPLETE parent with ORIGINAL and ALL32 claims, then review each patch independently applied to this parent. Accept faithful natural rephrasing; reject missing/added facts, changed conditions, uncertainty, causal links, timing or serious prose defects. Return {baseline_faithful:boolean,baseline_issues:[string],checked_claim_ids:[all32IDs],patches:[{id,faithful:boolean,issues:[string]}]}. Do not rewrite patches.'},allow_api)
        save_new(folder/'review.json',review)
        rows=review.get('patches',[])
        checked={p['id']:p for p in rows}
        if (review.get('baseline_faithful') is not True or review.get('baseline_issues') or
            len(review.get('checked_claim_ids',[]))!=32 or set(review['checked_claim_ids'])!={c['id'] for c in claims} or
            len(checked)!=len(rows) or set(checked)!={p['id'] for p in patches}):
            raise ValueError('Provider whole-source or exact patch-ID review failed')
        approved=[p for p in patches if checked[p['id']].get('faithful') is True and not checked[p['id']].get('issues')]
        save_new(folder/'bank.json',{'parent':parent,'patches':approved,'source_sha256':r.sha(source)})
        prefix=f'{REQUEST_PREFIX}r{number:02d}'
        files=[folder/'context.json',folder/'review.json',folder/'bank.json',
               r.RUN/'rounds'/(prefix+'-grok.request.json'),r.RUN/'rounds'/(prefix+'-grok.response.json')]
        save_new(folder/'bindings.json',{str(p.relative_to(r.RUN)):r.sha(p.read_text()) for p in files})
        seen=known_hashes(); known_before=set(seen); queued={}; singles=[]; made=[]
        for patch in approved:
            text=check_text(apply(parent['text'],[patch]),source); digest=r.sha(text)
            row={'patch_id':patch['id'],'sha256':digest,'new_unique':digest not in seen}
            if digest not in seen:
                cid=f'{ID_PREFIX}{number:02d}-s{len(made)+1:03d}'
                job={'id':cid,'phase':PHASE,'bank':number,'text':text,'sha256':digest,'source_sha256':r.sha(source),
                     'parent_id':parent['id'],'parent_sha256':parent['sha256'],'patch_ids':[patch['id']],
                     'created_at':r.now(),'combined_full_source_review':'pending','individual_patches_reviewed':True}
                save_new(D/'jobs'/(cid+'.json'),job);seen.add(digest);made.append(cid);row['job_id']=cid;queued[digest]=cid
            elif digest in known_before:
                score_pair(digest) # Known singles may be reused only with exact valid dual receipts.
            else:
                row['job_id']=queued[digest] # Same text from another approved patch; queue only once.
                row['same_bank_duplicate']=True
            singles.append(row)
        save_new(folder/'singles.json',{'bank':number,'new_unique':len(made),'candidate_ids':made,'singles':singles,
                                      'next':'Exact dual measurements before combination ranking'})
        print('Phase',PHASE,'bank',number,'saved',len(made),'new single-patch texts; exact measurements pending',flush=True)
        r.archive()


def bound_bank(number):
    source, claims=admitted();folder=D/'banks'/f'{ID_PREFIX}{number:02d}'
    for relative,digest in r.read(folder/'bindings.json').items():
        if r.sha((r.RUN/relative).read_text())!=digest: raise ValueError('Frozen Phase D bank evidence changed')
    bank=r.read(folder/'bank.json');parent=bank['parent']
    if parent['sha256']!=r.sha(parent['text']) or bank['source_sha256']!=r.sha(source) or parent['source_sha256']!=r.sha(source):
        raise ValueError('Bank parent/source binding differs')
    r.parent_approvals(parent,r.sha(source),claims)
    prefix=f'{REQUEST_PREFIX}r{number:02d}'
    request=r.read(r.RUN/'rounds'/(prefix+'-grok.request.json'));prompt=json.loads(request['prompt'])
    if (request.get('provider')!='xai' or request.get('model')!=r.MODELS['xai'] or
        prompt.get('source')!=source or prompt.get('claims')!=claims or prompt.get('current')!=parent['text']):
        raise ValueError('Review request differs from source/parent/model')
    receipt=r.read(r.RUN/'rounds'/(prefix+'-grok.response.json'));body=receipt['body']
    if receipt['http_status']!=200 or body.get('status')!='completed' or body.get('incomplete_details'):
        raise ValueError('Review provider response incomplete')
    output=''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    review=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',output.strip()))
    if review!=r.read(folder/'review.json'): raise ValueError('Review differs from actual saved response')
    submitted={p['id']:p for p in prompt['patches']};rows=review.get('patches',[])
    checked={p['id']:p for p in rows}
    if (len(submitted)!=len(prompt['patches']) or len(checked)!=len(rows) or set(checked)!=set(submitted) or
        review.get('baseline_faithful') is not True or review.get('baseline_issues') or
        len(review.get('checked_claim_ids',[]))!=32 or set(review['checked_claim_ids'])!={c['id'] for c in claims}):
        raise ValueError('Complete provider source/patch review missing')
    approved={k for k,v in checked.items() if v.get('faithful') is True and not v.get('issues')}
    if {p['id'] for p in bank['patches']}!=approved: raise ValueError('Approved patch set changed')
    for p in bank['patches']:
        if p!=r.valid_patch(parent['text'],p) or p!=submitted.get(p['id']): raise ValueError('Patch span or reviewer request binding differs')
    return bank


def ranked(bank):
    patches=bank['patches'];parent=bank['parent'];base=list(map(logit,score_pair(parent['sha256'])))
    deltas=[]
    for p in patches:
        measured=score_pair(r.sha(apply(parent['text'],[p])))
        deltas.append([logit(value)-original for value,original in zip(measured,base)])
    states=[((),tuple(base))];result=[]
    for width in range(1,7):
        expanded=[]
        for indices,values in states:
            for i in range(indices[-1]+1 if indices else 0,len(patches)):
                p=patches[i]
                if any(not (p['end']<=patches[j]['start'] or p['start']>=patches[j]['end']) for j in indices): continue
                new=indices+(i,);predicted=tuple(x+y for x,y in zip(values,deltas[i]))
                expanded.append((new,predicted))
        expanded.sort(key=lambda x:(max(x[1]),sum(x[1]),x[0]));states=expanded[:BEAM]
        if width>=2: result.extend(states)
    result.sort(key=lambda x:(max(x[1]),sum(x[1]),x[0]))
    return result


def combine(number):
    with coordinator_lock():
        source,_=admitted();folder=D/'banks'/f'{ID_PREFIX}{number:02d}'
        if not 1<=number<=MAX_BANKS: raise ValueError('Unknown bank')
        if (folder/'complete.json').exists() or any((D/'jobs').glob(f'{ID_PREFIX}{number:02d}-c*.json')):
            raise RuntimeError('Combinations already started; immutable evidence retained')
        bank=bound_bank(number);all_jobs=jobs();own=[j for j in all_jobs if j['bank']==number]
        maximum=min(PER_BANK-len(own),MAX_TEXTS-len(all_jobs))
        if maximum<=0: raise RuntimeError('No remaining distinct-text capacity')
        candidates=[];seen=known_hashes()
        for indices,predicted in ranked(bank):
            chosen=[bank['patches'][i] for i in indices]
            text=check_text(apply(bank['parent']['text'],chosen),source);digest=r.sha(text)
            if digest in seen: continue
            seen.add(digest)
            candidates.append({'text':text,'sha256':digest,'patch_ids':[p['id'] for p in chosen],
                'ranking_only_predicted_logits':predicted,'prediction_is_not_a_measurement':True})
        primary=math.floor(maximum*.8);chosen=candidates[:primary];remainder=candidates[primary:]
        random.Random(SEED+number).shuffle(remainder);chosen+=remainder[:maximum-len(chosen)]
        made=[]
        for row in chosen:
            cid=f'{ID_PREFIX}{number:02d}-c{len(made)+1:03d}'
            job={**row,'id':cid,'phase':PHASE,'bank':number,'source_sha256':r.sha(source),
                 'parent_id':bank['parent']['id'],'parent_sha256':bank['parent']['sha256'],
                 'created_at':r.now(),'combined_full_source_review':'pending','individual_patches_reviewed':True}
            save_new(D/'jobs'/(cid+'.json'),job);made.append(cid)
        save_new(folder/'complete.json',{'at':r.now(),'bank':number,'new_singles':len(own),'new_combinations':len(made),
            'new_unique':len(own)+len(made),'candidate_ids':made,'ranked_unused_pool':len(candidates),
            'prediction_is_not_a_measurement':True,'scoring':'pending'})
        print('Phase',PHASE,'bank',number,'generated',len(made),'new combinations; exact measurements pending',flush=True)
        r.archive()


def status():
    source,claims=r.bound_source();rows=[];all_jobs=jobs()
    for job in all_jobs:
        if job.get('source_sha256')!=r.sha(source): raise ValueError('Candidate source identity differs')
        try:d,v=score_pair(job['sha256'])
        except FileNotFoundError:continue
        try:reviewers=r.parent_approvals(job,r.sha(source),claims)
        except ValueError:reviewers=[]
        rows.append({'id':job['id'],'sha256':job['sha256'],'desklib':d,'vanguard':v,'maximum':max(d,v),
                     'source_reviewers':reviewers,'review':'source_verified' if reviewers else 'pending'})
    rows.sort(key=lambda x:(x['maximum'],x['desklib']+x['vanguard'],x['id']))
    result={'at':r.now(),'phase':PHASE,'unique_generated':len(all_jobs),'paired':len(rows),
            'new_provider_requests_attempted':sum(k.startswith(REQUEST_PREFIX) for k in r.ledger()['requests']),
            'global_estimated_or_reserved_api_usd':r.cost(r.ledger()),'best':rows[:20],'scores':rows,
            'selected_verified':next((x for x in rows if x['review']=='source_verified'),None)}
    for label,threshold in ((30,.30),(10,.10),(2,.02)):
        eligible=[x for x in rows if x['maximum']<threshold and x['review']=='source_verified']
        result[f'verified_below_both_{label}']=len(eligible)
        gate=D/f'verified-gate-{label}.json'
        if eligible and not gate.exists():
            selected=eligible[0]
            save_new(gate,{'at':r.now(),'phase':PHASE,'selected':selected,'threshold':threshold,
                'job':r.read(D/'jobs'/(selected['id']+'.json')),
                'measurements':{d:r.read(r.RUN/'scores'/d/(selected['sha256']+'.json')) for d in ('desklib','vanguard')},
                'scope':'Exact one-source adaptive result; no held-out efficacy or universal detection/watermark guarantee.'})
    r.save(D/'status.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='scores'},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bank','combine','status'])
    p.add_argument('--bank',type=int,default=1);p.add_argument('--allow-api',action='store_true');a=p.parse_args()
    if a.action=='bank':generate_bank(a.bank,a.allow_api)
    elif a.action=='combine':combine(a.bank)
    else:status()
