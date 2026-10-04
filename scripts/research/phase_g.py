"""Prospective zero-provider expansion of an exact same-parent approved pool.

Preparation only reconstructs and hashes a bounded pool. It creates no test jobs
and performs no detector inference. Activation requires separate root approval.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import random
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r
from scripts.research import phase_e as e
from scripts.research import phase_f as f
from scripts.research.phase_b import apply,logit,score_pair
from scripts.research.phase_d import check_text,save_new

G=r.RUN/'phase-g'
CAP,BEAM,SEED,MAX_WIDTH=1000,5000,6100440,10
PLAN_SHA='f129eb52bb1790db10b5a648e61eebdbdf6e5ce801954bb0f868370a63667ed4'


def approved_pool():
    banks=[('e01',e.core.bound_bank(1)),('e02',e.core.bound_bank(2)),('f01',f.bound_bank())]
    parent=banks[0][1]['parent'];source,claims=r.bound_source()
    r.parent_approvals(parent,r.sha(source),claims)
    pooled={}
    for name,bank in banks:
        if bank['parent']!=parent or bank['source_sha256']!=r.sha(source):raise ValueError('Merged banks require one exact parent/source')
        for patch in bank['patches']:
            if patch!=r.valid_patch(parent['text'],patch):raise ValueError('An approved patch no longer passes unchanged guards')
            key=(patch['find'],patch['replace'],patch['start'],patch['end'])
            pooled.setdefault(key,{'patch':patch,'provenance':[]})['provenance'].append({'bank':name,'patch_id':patch['id']})
    patches=[]
    for i,(_,item) in enumerate(sorted(pooled.items(),key=lambda item:(item[0][2],item[0][3],item[0][0],item[0][1])),1):
        patches.append({**item['patch'],'id':f'g-p{i:03d}','provenance':item['provenance']})
    files=set()
    for phase,folders in [('e',('e01','e02')),('f',('',))]:
        root=r.RUN/('phase-'+phase)
        files.update([root/'approval.json',root/'protocol.json',root/'plan-draft.json'])
        for folder in folders:
            base=root/'banks'/folder if folder else root
            binding=base/'bindings.json';files.add(binding)
            files.update(r.RUN/relative for relative in r.read(binding))
    return {'parent':parent,'patches':patches,'source_sha256':r.sha(source),
            'frozen_bank_files':{str(path.relative_to(r.RUN)):r.sha(path.read_text()) for path in sorted(files)}}


def rank_pool(pool):
    parent,patches=pool['parent'],pool['patches'];base=list(map(logit,score_pair(parent['sha256'])))
    deltas=[[logit(value)-original for value,original in zip(score_pair(r.sha(apply(parent['text'],[patch]))),base)] for patch in patches]
    states=[((),tuple(base))];ranked=[]
    for width in range(1,MAX_WIDTH+1):
        expanded=[]
        for indices,values in states:
            for i in range(indices[-1]+1 if indices else 0,len(patches)):
                patch=patches[i]
                if any(not(patch['end']<=patches[j]['start'] or patch['start']>=patches[j]['end']) for j in indices):continue
                expanded.append((indices+(i,),tuple(x+y for x,y in zip(values,deltas[i]))))
        expanded.sort(key=lambda row:(max(row[1]),sum(row[1]),row[0]));states=expanded[:BEAM]
        if width>=2:ranked.extend(states)
    return sorted(ranked,key=lambda row:(max(row[1]),sum(row[1]),row[0]))


def prepare():
    if (G/'plan-draft.json').exists():raise RuntimeError('Prospective G plan already frozen; no implicit replacement')
    if any((G/'jobs').glob('*.json')):raise RuntimeError('No G jobs allowed during preparation')
    pool=approved_pool();source,_=r.bound_source();seen=f.known_hashes();rows=[]
    for indices,predicted in rank_pool(pool):
        text=check_text(apply(pool['parent']['text'],[pool['patches'][i] for i in indices]),source);digest=r.sha(text)
        if digest in seen:continue
        seen.add(digest);rows.append({'indices':indices,'sha256':digest,'ranking_only_predicted_logits':predicted,
                                    'prediction_is_not_a_measurement':True})
    if len(rows)<CAP:raise RuntimeError('Bounded pool does not contain1000 unused distinct concrete texts')
    save_new(G/'approved-pool.json',pool)
    save_new(G/'ranked-unused-pool.json',{'at':r.now(),'count':len(rows),'rows':rows,'measured_candidates':0,'new_provider_calls':0})
    plan={'created_at':r.now(),'phase':'G','status':'prospective_not_authorized','source_sha256':r.sha(source),
          'parent_id':pool['parent']['id'],'parent_sha256':pool['parent']['sha256'],
          'purpose':'No-API measured expansion of unused combinations from29 already-approved E/F edits on one exact parent, toward both-below2.',
          'maximum_new_distinct_texts':CAP,'new_provider_calls':0,'shared_global_api_budget_usd':1.5,
          'beam_width':BEAM,'widths':[2,MAX_WIDTH],'seed':SEED,'sampling':'800 lowest predicted maximum logits plus200 seeded alternatives from unused retained beam candidates; rankings never count as measured scores.',
          'prerequisites':'Phase F complete with300 distinct exact dual measurements and a source-reviewed selected result; no existing verified both-below2 gate; separate rootapproval bound to this exact plan.',
          'approved_patch_count':len(pool['patches']),'bounded_unused_distinct_pool':len(rows),
          'approved_pool_sha256':r.sha((G/'approved-pool.json').read_text()),'ranked_unused_pool_sha256':r.sha((G/'ranked-unused-pool.json').read_text()),
          'history_exclusion':'Source, recoverybaseline, historical10, allA–F candidates and bankparents; G exacthash de-dup. Every selected new text must be reconstructed from nonoverlapping exact approved patches.',
          'measurements':'Same pinned local full-document Desklib/Vanguard inference and precision settings; no external detector service or new checkpoint. Candidate scores only from actual exact full-text receipts.',
          'eligibility':'Two independent exact-hash complete32claim and whole-source/quality approvals before threshold promotion; immutable first below10 gate retained.',
          'stop':'No new paid calls. Stop job admission if both-below2 verified, otherwise at most1000 newunique tests; preserve actual generated/measured counts and all prior phase caps.',
          'frozen_shared_code_sha256':{p:r.sha((r.ROOT/p).read_text()) for p in ['scripts/research/recovery.py','scripts/research/phase_b.py','scripts/research/phase_d.py','scripts/research/phase_e.py','scripts/research/phase_f.py','scripts/research/score.py']},
          'scope':'One-source adaptive in-sample research; no heldout retuning, universal detector/watermark or authorship guarantee.'}
    save_new(G/'plan-draft.json',plan)
    print(json.dumps({'plan_sha256':r.sha(json.dumps(plan,sort_keys=True)),'approved_patch_count':len(pool['patches']),
                      'bounded_unused_distinct_pool':len(rows),'new_test_jobs':0,'new_inference':0,'new_provider_calls':0}),flush=True)
    r.archive()


@contextmanager
def locked():
    G.mkdir(parents=True,exist_ok=True)
    with (G/'runner.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def admitted():
    if not (G/'approval.json').exists():raise RuntimeError('Phase G has not been authorized')
    plan,approval=r.read(G/'plan-draft.json'),r.read(G/'approval.json')
    expected={'authorized':True,'phase':'G','plan_sha256':PLAN_SHA,'max_new_unique':CAP,
              'new_api_calls':0,'global_budget_usd':r.LIMIT_USD}
    if r.sha(json.dumps(plan,sort_keys=True))!=PLAN_SHA or any(approval.get(k)!=v for k,v in expected.items()):
        raise ValueError('G approval or frozen prospective plan differs')
    if r.cost(r.ledger())>r.LIMIT_USD:raise RuntimeError('Global research commitment exceeds limit')
    for relative,digest in plan['frozen_shared_code_sha256'].items():
        if r.sha((r.ROOT/relative).read_text())!=digest:raise ValueError('G frozen shared helper changed')
    for name,key in (('approved-pool.json','approved_pool_sha256'),('ranked-unused-pool.json','ranked_unused_pool_sha256')):
        if r.sha((G/name).read_text())!=plan[key]:raise ValueError('Frozen G pool/ranking evidence changed')
    pool=r.read(G/'approved-pool.json')
    if pool!=approved_pool():raise ValueError('Merged pool no longer matches exact reviewed E/F banks')
    source,claims=r.bound_source()
    if pool['source_sha256']!=r.sha(source) or pool['parent']['sha256']!=plan['parent_sha256']:
        raise ValueError('G parent/source identity differs')
    r.parent_approvals(pool['parent'],r.sha(source),claims)
    final=r.read(f.F/'final-complete.json');fjobs=f.jobs()
    if final.get('unique_generated')!=300 or final.get('paired')!=300 or len(fjobs)!=300:
        raise RuntimeError('Phase F must finish300 exact paired distinct texts before G')
    by_id={job['id']:job for job in fjobs}
    for job in fjobs:
        if job['source_sha256']!=r.sha(source):raise ValueError('F source differs before G admission')
        score_pair(job['sha256'])
    selected=final.get('selected_verified')
    if not selected or selected['id'] not in by_id:raise ValueError('F final source-reviewed result missing')
    job=by_id[selected['id']]
    if selected['sha256']!=job['sha256']:raise ValueError('F selected final identity differs')
    r.parent_approvals(job,r.sha(source),claims)
    pair=score_pair(job['sha256'])
    if pair!=[selected['desklib'],selected['vanguard']]:raise ValueError('F selected final scores differ from exact receipts')
    target_paths=[r.RUN/'verified-gate-2.json',*[r.RUN/f'phase-{p}/verified-gate-2.json' for p in ('b','d','e','f','g')]]
    if any(path.exists() for path in target_paths):raise RuntimeError('Both-below2 verified; no further G job admission')
    return plan,approval,pool


def jobs():
    rows=[r.read(p) for p in sorted((G/'jobs').glob('*.json'))]
    if len(rows)>CAP or len({j['sha256'] for j in rows})!=len(rows):raise ValueError('G distinct-text cap or uniqueness violated')
    for job in rows:
        if job.get('phase')!='G' or job['sha256']!=r.sha(job['text']):raise ValueError('G exact text identity differs')
    return rows


def select_rows(rows):
    if len(rows)<CAP:raise ValueError('Insufficient unused ranked candidates')
    selected=list(rows[:800]);remaining=list(rows[800:]);random.Random(SEED).shuffle(remaining)
    return selected+remaining[:200]


def generate():
    with locked():
        plan,approval,pool=admitted()
        if jobs() or (G/'complete.json').exists() or (G/'protocol.json').exists():
            raise RuntimeError('G already started; no overwrite or implicit restart')
        source,_=r.bound_source();ranked=r.read(G/'ranked-unused-pool.json')
        if ranked['count']!=len(ranked['rows']) or ranked['count']!=plan['bounded_unused_distinct_pool']:
            raise ValueError('Bounded G candidate count differs')
        selected=select_rows(ranked['rows']);seen=f.known_hashes();prepared=[]
        for row in selected:
            indices=row['indices']
            if (not isinstance(indices,list) or not 2<=len(indices)<=MAX_WIDTH or len(set(indices))!=len(indices) or
                any(not isinstance(i,int) or not 0<=i<len(pool['patches']) for i in indices)):
                raise ValueError('Invalid prospective combination indices')
            patches=[pool['patches'][i] for i in indices]
            text=apply(pool['parent']['text'],patches)
            if text is None:raise ValueError('Prospective G combination overlaps')
            text=check_text(text,source);digest=r.sha(text)
            if digest!=row['sha256'] or digest in seen:raise ValueError('Prospective G text changed or already exists in history')
            seen.add(digest);prepared.append({**row,'text':text,'patch_ids':[p['id'] for p in patches]})
        protocol={**plan,'status':'activated','activated_at':r.now(),'approval':approval,
                  'runner_sha256':{p:r.sha((r.ROOT/p).read_text()) for p in ('scripts/research/phase_g.py','scripts/research/score_phase_g.py')},
                  'selection_sha256':r.sha(json.dumps(selected,sort_keys=True)),'new_provider_calls':0}
        save_new(G/'protocol.json',protocol)
        for i,row in enumerate(prepared,1):
            cid=f'g01-c{i:04d}'
            save_new(G/'jobs'/(cid+'.json'),{**row,'id':cid,'phase':'G','source_sha256':r.sha(source),
                'parent_id':pool['parent']['id'],'parent_sha256':pool['parent']['sha256'],'created_at':r.now(),
                'combined_full_source_review':'pending','individual_patches_reviewed':True})
        save_new(G/'complete.json',{'at':r.now(),'unique_generated':len(prepared),'new_api_calls':0,'scoring':'pending'})
        print('Phase G generated',len(prepared),'new distinct exact texts; no provider calls; measurements pending',flush=True);r.archive()


def status():
    source,claims=r.bound_source();all_jobs=jobs();rows=[]
    for job in all_jobs:
        if job.get('source_sha256')!=r.sha(source):raise ValueError('G job source differs')
        try:d,v=score_pair(job['sha256'])
        except FileNotFoundError:continue
        try:reviewers=r.parent_approvals(job,r.sha(source),claims)
        except ValueError:reviewers=[]
        rows.append({'id':job['id'],'sha256':job['sha256'],'desklib':d,'vanguard':v,'maximum':max(d,v),
                     'source_reviewers':reviewers,'review':'source_verified' if reviewers else 'pending'})
    rows.sort(key=lambda x:(x['maximum'],x['desklib']+x['vanguard'],x['id']))
    result={'at':r.now(),'phase':'G','unique_generated':len(all_jobs),'paired':len(rows),'new_api_calls':0,
            'global_estimated_or_reserved_api_usd':r.cost(r.ledger()),'best':rows[:20],'scores':rows,
            'selected_verified':next((x for x in rows if x['review']=='source_verified'),None)}
    for label,threshold in ((30,.30),(10,.10),(2,.02)):
        eligible=[x for x in rows if x['maximum']<threshold and x['review']=='source_verified']
        result[f'verified_below_both_{label}']=len(eligible);gate=G/f'verified-gate-{label}.json'
        if eligible and not gate.exists():
            selected=eligible[0]
            save_new(gate,{'at':r.now(),'phase':'G','threshold':threshold,'selected':selected,
                'job':r.read(G/'jobs'/(selected['id']+'.json')),
                'measurements':{d:r.read(r.RUN/'scores'/d/(selected['sha256']+'.json')) for d in ('desklib','vanguard')},
                'scope':'One-source adaptive result; no held-out or general detector/watermark efficacy claim.'})
    r.save(G/'status.json',result);print(json.dumps({k:v for k,v in result.items() if k!='scores'},indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','generate','status']);a=p.parse_args();globals()[a.action]()
