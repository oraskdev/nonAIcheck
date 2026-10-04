"""Separately approved continuation after D's complete, verified below10 result.

An isolated module instance shares the audited runner without changing phase D's
configuration. E has its own directory, identifiers, approval, limits and history.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r
from scripts.research.phase_b import score_pair

E=r.RUN/'phase-e'
PLAN_SHA='d5511259ee38f90aaf2ee5b805e7c41402afc19ca6664ca2e040d4b2da8a2919'
_spec=importlib.util.spec_from_file_location('phase_e_isolated_core',Path(__file__).with_name('phase_d.py'))
core=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)
core.D=E
core.PHASE,core.ID_PREFIX,core.REQUEST_PREFIX='E','e','phase-e-'
core.MAX_BANKS,core.MAX_CALLS,core.MAX_TEXTS,core.PER_BANK=2,6,300,150
core.OUTPUT_LIMIT,core.PATCH_MIN,core.PATCH_MAX=4500,14,18
core.PARENT_PHASES=('A','B','D','E')
core.EXTRA_APPROVAL_FIELDS={'max_output_tokens':4500,'patch_range':[14,18]}
core.SEED=6100420
core.PLAN_SHA=PLAN_SHA
_base_admitted=core.admitted


def prerequisites():
    if not (E/'approval.json').exists():
        raise RuntimeError('Phase E has not been authorized')
    plan=r.read(E/'plan-draft.json')
    if r.sha(json.dumps(plan,sort_keys=True))!=PLAN_SHA:
        raise ValueError('Frozen Phase E plan changed')
    for relative,digest in plan['frozen_shared_code_sha256'].items():
        if r.sha((r.ROOT/relative).read_text())!=digest:
            raise ValueError('Phase E shared code differs from prospective frozen version')
    source,claims=r.bound_source()
    gate_path=r.RUN/'phase-d/verified-gate-10.json'
    if r.sha(gate_path.read_text())!=plan['first_verified_d_below10_checkpoint_sha256']:
        raise ValueError('First verified below10 checkpoint changed')
    gate=r.read(gate_path);candidate=gate['job']
    if candidate['sha256']!=r.sha(candidate['text']) or candidate.get('source_sha256')!=r.sha(source):
        raise ValueError('Below10 checkpoint text/source identity differs')
    r.parent_approvals(candidate,r.sha(source),claims)
    if max(score_pair(candidate['sha256']))>=.10:
        raise RuntimeError('Both-below10 prerequisite has not been verified')
    jobs=[r.read(p) for p in (r.RUN/'phase-d/jobs').glob('*.json')]
    if len(jobs)!=450 or len({j['sha256'] for j in jobs})!=450:
        raise RuntimeError('D must finish450 distinct candidates before E activation')
    for job in jobs:
        if (job.get('phase')!='D' or job['sha256']!=r.sha(job['text']) or
            job.get('source_sha256')!=r.sha(source)):
            raise ValueError('Phase D exact text/source binding differs')
        score_pair(job['sha256'])
    return _base_admitted()


core.admitted=prerequisites


def generate_bank(number,allow_api=False):
    return core.generate_bank(number,allow_api)


def combine(number):
    return core.combine(number)


def status():
    return core.status()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['bank','combine','status'])
    p.add_argument('--bank',type=int,default=1);p.add_argument('--allow-api',action='store_true');a=p.parse_args()
    if a.action=='bank':generate_bank(a.bank,a.allow_api)
    elif a.action=='combine':combine(a.bank)
    else:status()
