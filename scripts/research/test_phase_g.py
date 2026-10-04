"""Offline no-charge authorization, deterministic selection and immutable counts."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.research import recovery as r
from scripts.research import phase_g as g


class PhaseGSafety(unittest.TestCase):
    def test_requires_new_approval_before_generating(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(g,'G',Path(folder)),patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'not been authorized'):g.generate()
            invoke.assert_not_called()
            self.assertEqual(list((Path(folder)/'jobs').glob('*.json')),[])

    def test_deterministic_800_ranked_200_alternatives(self):
        rows=[{'indices':[i,i+1],'sha256':str(i),'ranking_only_predicted_logits':[i,i]} for i in range(2000)]
        first=g.select_rows(rows);second=g.select_rows(rows)
        self.assertEqual(first,second)
        self.assertEqual(len(first),1000)
        self.assertEqual(first[:800],rows[:800])
        self.assertEqual(len({r['sha256'] for r in first}),1000)
        self.assertTrue(all(int(r['sha256'])>=800 for r in first[800:]))
        with self.assertRaises(ValueError):g.select_rows(rows[:999])

    def test_completed_or_partial_run_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(g,'G',Path(folder)), \
             patch.object(g,'admitted',return_value=({}, {}, {})),patch.object(g,'jobs',return_value=[{}]), \
             patch.object(r,'call') as invoke:
            with self.assertRaisesRegex(RuntimeError,'already started'):g.generate()
            invoke.assert_not_called()

    def test_job_hash_and_uniqueness_are_recomputed(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(g,'G',Path(folder)):
            text='A concrete test document.'
            job={'id':'g01-c0001','phase':'G','text':text,'sha256':r.sha(text)}
            r.save(Path(folder)/'jobs/g01-c0001.json',job)
            self.assertEqual(len(g.jobs()),1)
            r.save(Path(folder)/'jobs/g01-c0002.json',{**job,'id':'g01-c0002'})
            with self.assertRaisesRegex(ValueError,'uniqueness'):g.jobs()
            (Path(folder)/'jobs/g01-c0002.json').unlink()
            r.save(Path(folder)/'jobs/g01-c0001.json',{**job,'text':'Altered after hashing.'})
            with self.assertRaisesRegex(ValueError,'identity'):g.jobs()


if __name__=='__main__':unittest.main()
