"""Offline exhaustive-review, budget boundary and namespace tests for Phase F."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.research import recovery as r
from scripts.research import phase_f as f


class PhaseFSafety(unittest.TestCase):
    def fixture(self):
        text='Title\n\nI should learn about care before spending more.'
        p=r.valid_patch(text,{'id':'p1','find':'I should learn about care before spending more.',
                              'replace':'Before spending more, I should learn about care.'})
        return {'text':text,'sha256':r.sha(text)},[p]

    def test_no_approval_no_provider_call(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(f,'F',Path(folder)),patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'not been authorized'):f.call('openai',{},True)
            invoke.assert_not_called()

    def test_exhaustive_ids_actions_reasons_and_repairs(self):
        parent,proposals=self.fixture()
        valid={'id':'p1','action':'accept','reason':'Meaning is preserved'}
        self.assertEqual(f.apply_decisions(parent,proposals,{'decisions':[valid]}),proposals)
        for rows in ([],[valid,valid],[{**valid,'id':'other'}],[{**valid,'reason':''}],
                     [{**valid,'action':'repair','replace':'Before spending more, I will learn about care.'}],
                     [{**valid,'find':'different span'}],[{**valid,'replace':'Silently different replacement'}]):
            with self.assertRaises(ValueError):f.apply_decisions(parent,proposals,{'decisions':rows})
        self.assertEqual(f.apply_decisions(parent,proposals,{'decisions':[{**valid,'action':'reject'}]}),[])

    def test_all_rejected_stops_before_grok(self):
        parent,proposals=self.fixture();answer={'decisions':[{'id':'p1','action':'reject','reason':'Omitted qualification'}]}
        with tempfile.TemporaryDirectory() as folder,patch.object(f,'F',Path(folder)), \
             patch.object(f,'admitted',return_value=(parent['text'],[],parent,proposals)), \
             patch.object(f,'call',return_value=answer) as invoke,patch.object(r,'archive'):
            r.save(Path(folder)/'prospective-openai-prompt.json',{})
            f.review(True)
            self.assertEqual(invoke.call_count,1)
            self.assertEqual(invoke.call_args.args[0],'openai')
            self.assertFalse(r.read(Path(folder)/'no-retained-proposals.json')['grok_called'])

    def test_actual_system_compact_prompt_and_output_cap(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(r,'RUN',Path(folder)), \
             patch.object(f,'admitted'),patch.object(r,'ledger',return_value={'requests':{}}),patch.object(r,'call') as invoke:
            f.call('openai',{'a':1,'b':2},True)
            args=invoke.call_args.args
            self.assertEqual(args[1],'phase-f-openai');self.assertEqual(args[2],r.BASE_SYSTEM)
            self.assertEqual(args[3],'{"a":1,"b":2}')
            self.assertEqual(invoke.call_args.kwargs['max_output_tokens'],4500)
            with self.assertRaises(ValueError):f.call('anthropic',{},True)

    def test_second_call_budget_denial_happens_before_transport(self):
        import httpx
        with tempfile.TemporaryDirectory() as folder,patch.object(r,'RUN',Path(folder)), \
             patch.object(f,'admitted'),patch.object(r,'load_keys',return_value={'xai':'test-placeholder'}), \
             patch.object(httpx,'Client') as transport:
            usage={'input_tokens':0,'output_tokens':1000}
            r.save(Path(folder)/'ledger.json',{'limit_usd':1.5,'requests':{'prior':{'reserved_usd':1.48},'phase-f-openai':{'reserved_usd':.09,'actual_usd':.01,'usage':usage,'status':'response_saved'}}})
            r.save(Path(folder)/'rounds/phase-f-openai.response.json',{'http_status':200,'body':{'status':'completed','usage':usage}})
            with self.assertRaisesRegex(RuntimeError,'budget exhausted'):f.call('xai',{},True)
            transport.assert_not_called()
            self.assertNotIn('phase-f-grok',r.ledger()['requests'])

    def test_grok_requires_first_actual_usage(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(r,'RUN',Path(folder)), \
             patch.object(f,'admitted'),patch.object(r,'ledger',return_value={'requests':{}}),patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'actual usage reconciliation'):f.call('xai',{},True)
            invoke.assert_not_called()

    def test_grok_rejections_need_explicit_boolean_and_issues(self):
        _,proposals=self.fixture();claims=[{'id':f'G{i:02d}'} for i in range(1,33)]
        base={'baseline_faithful':True,'baseline_issues':[],'checked_claim_ids':[c['id'] for c in claims]}
        for row in ({'id':'p1','faithful':False,'issues':[]},{'id':'p1','faithful':True},
                    {'id':'p1','faithful':'true','issues':[]},{'id':'p1','faithful':False,'issues':['']}):
            with self.assertRaises(ValueError):f.review_set(claims,proposals,{**base,'patches':[row]})
        self.assertEqual(f.review_set(claims,proposals,{**base,'patches':[{'id':'p1','faithful':False,'issues':['Changes a condition']}]}),[])

    def test_zero_capacity_never_generates_one_extra_job(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(f,'F',Path(folder)), \
             patch.object(f,'admitted',return_value=('Title\n\nBody.',[],{},[])), \
             patch.object(f,'bound_bank',return_value={}),patch.object(f,'jobs',return_value=[{}]*300),patch.object(f,'ranked') as rank:
            with self.assertRaisesRegex(RuntimeError,'No remaining'):f.combine()
            rank.assert_not_called()


if __name__=='__main__':unittest.main()
