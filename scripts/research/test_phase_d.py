"""Offline Phase D admission, uniqueness and exact-measurement ranking checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import phase_d as d
from scripts.research import recovery as r


class PhaseDSafety(unittest.TestCase):
    def test_unapproved_phase_cannot_charge(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(d,'D',Path(directory)), patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'not been authorized'):
                d.generate_bank(1,True)
            invoke.assert_not_called()

    def test_request_cap_and_invalid_bank_cannot_charge(self):
        requests={f'phase-d-existing{i}':{} for i in range(9)}
        with patch.object(d,'admitted'), patch.object(r,'ledger',return_value={'requests':requests}), patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'nine-request cap'):
                d.call('anthropic',1,{},True)
            with self.assertRaises(ValueError):d.call('anthropic',4,{},True)
            invoke.assert_not_called()

    def test_verified_target_in_phase_b_stops_new_paid_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            run=Path(directory)
            r.save(run/'phase-b/verified-gate-2.json',{'verified':True})
            with patch.object(r,'RUN',run), patch.object(d,'D',run/'phase-d'), \
                 patch.object(d,'admitted'), patch.object(r,'ledger',return_value={'requests':{}}), \
                 patch.object(r,'call') as invoke:
                with self.assertRaisesRegex(RuntimeError,'Both-below2'):
                    d.call('anthropic',1,{},True)
                invoke.assert_not_called()

    def test_immutable_jobs_and_distinct_count(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(d,'D',Path(directory)):
            job={'phase':'D','id':'d01-s001','text':'one','sha256':r.sha('one')}
            path=Path(directory)/'jobs/d01-s001.json'
            d.save_new(path,job)
            with self.assertRaisesRegex(RuntimeError,'overwrite'):d.save_new(path,job)
            r.save(Path(directory)/'jobs/d01-s002.json',{**job,'id':'d01-s002'})
            with self.assertRaisesRegex(ValueError,'uniqueness'):d.jobs()

    def test_combination_ranking_requires_exact_single_scores(self):
        text='Title\n\nOne sentence is here. Another sentence is here.'
        specs=[{'id':'a','find':'One sentence is here.','replace':'The first line is here.'},
               {'id':'b','find':'Another sentence is here.','replace':'The second line is here.'}]
        patches=[r.valid_patch(text,s) for s in specs]
        self.assertTrue(all(patches))
        bank={'parent':{'text':text,'sha256':r.sha(text)},'patches':patches}
        with patch.object(d,'score_pair',side_effect=[[.5,.5],[.3,.4],[.4,.3]]) as exact:
            ranked=d.ranked(bank)
            self.assertEqual(exact.call_count,3)
            self.assertEqual(ranked[0][0],(0,1))
        with patch.object(d,'score_pair',side_effect=FileNotFoundError('unmeasured')):
            with self.assertRaises(FileNotFoundError):d.ranked(bank)

    def test_zero_capacity_does_not_emit_candidate(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(d,'D',Path(directory)), \
             patch.object(d,'admitted',return_value=('Title\n\nBody.',[])), \
             patch.object(d,'bound_bank',return_value={}), \
             patch.object(d,'jobs',return_value=[{'bank':1}]*150), patch.object(d,'ranked') as rank:
            with self.assertRaisesRegex(RuntimeError,'No remaining distinct-text capacity'):d.combine(1)
            rank.assert_not_called()
            self.assertEqual(list((Path(directory)/'jobs').glob('*.json')),[])


if __name__=='__main__':unittest.main()
