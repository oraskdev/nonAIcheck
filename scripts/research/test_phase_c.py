"""Offline scope, source and no-charge admission checks for Phase C."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import phase_c as c
from scripts.research import recovery as r


class PhaseCSafety(unittest.TestCase):
    def test_requires_separate_authorization_before_any_call(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(c,"C",Path(directory)), patch.object(r,"call") as invoke:
            with self.assertRaisesRegex(RuntimeError,"not been authorized"):
                c.initialize(True)
            invoke.assert_not_called()

    def test_numeric_title_and_paragraph_integrity(self):
        source="Title\n\nI may buy 3 pots.\n\nMy budget is $60."
        self.assertEqual(c.check_text(source,source),source)
        for modified in (source.replace("3","4"), source.replace("Title","Other"), source.replace("\n\nMy"," My")):
            with self.assertRaises(ValueError): c.check_text(modified,source)

    def test_bank_above_competitiveness_gate_makes_no_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            source="Title\n\nI may buy 3 pots.\n\nMy budget is $60."
            r.save(path/"jobs/c00-draft.json",{"id":"c00-draft","text":source,"sha256":r.sha(source),
                "source_sha256":r.sha(source),"provider_review_faithful":True})
            with patch.object(c,"C",path), patch.object(c,"admitted",return_value=(source,[])), \
                 patch.object(c,"score_pair",return_value=[.36,.05]), patch.object(c,"call") as invoke:
                c.bank(True)
                invoke.assert_not_called()
                self.assertFalse(r.read(path/"admission-result.json")["admitted"])

    def test_six_request_cap_is_additional_to_global_budget(self):
        requests={f"phase-c-existing{i}":{} for i in range(6)}
        with patch.object(c,"admitted"), patch.object(r,"ledger",return_value={"requests":requests}), patch.object(r,"call") as invoke:
            with self.assertRaisesRegex(RuntimeError,"six-request limit"):
                c.call("anthropic","new",{},True)
            invoke.assert_not_called()


if __name__=="__main__": unittest.main()
