"""Offline integrity tests; no provider calls or inference."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import recovery as r


class RecoveryIntegrity(unittest.TestCase):
    def test_patch_rejects_numeric_or_modal_change(self):
        text = "Title\n\nI may start with 3 containers in spring."
        p = {"id": "p1", "find": text.split("\n\n")[1], "replace": "I may begin with 3 containers in spring."}
        self.assertIsNotNone(r.valid_patch(text, p))
        self.assertIsNone(r.valid_patch(text, {**p, "replace": p["replace"].replace("3", "4")}))
        self.assertIsNone(r.valid_patch(text, {**p, "replace": p["replace"].replace("may", "will")}))

    def test_patch_rejects_invisible_and_duplicate_span(self):
        text = "Title\n\nThe same sentence appears here."
        p = {"id": "p1", "find": text.split("\n\n")[1], "replace": "The same sentence appears\u200b here."}
        self.assertIsNone(r.valid_patch(text, p))
        self.assertIsNone(r.valid_patch(text + " " + p["find"], {**p, "replace": "This sentence is written here."}))

    def test_record_rejects_wrong_revision_nan_partial(self):
        record = {"sha256": "hash", "revision": r.VANG_REV, "measurement": {
            "model": "ShantanuT01/vanguard-ai-text-detector", "revision": r.VANG_REV,
            "coverage": "full_document", "tokens_assessed": 400, "ai_score": .1,
            "dtype": "float32", "reference_compile": False, "attention": "sdpa"}}
        r.validate_score(record, "hash", "vanguard", r.VANG_REV)
        for change in ({"ai_score": float("nan")}, {"revision": "other"}, {"coverage": "partial"}, {"tokens_assessed": 0}):
            with self.assertRaises(ValueError):
                r.validate_score({**record, "measurement": {**record["measurement"], **change}}, "hash", "vanguard", r.VANG_REV)

    def test_completed_round_makes_no_calls_or_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "rounds").mkdir(); (run / "jobs").mkdir()
            text = "Title\n\nThis is the original body."
            r.save(run / "baseline.json", {"id": "base", "text": text, "sha256": r.sha(text)})
            (run / "source.txt").write_text(text)
            r.save(run / "claims.json", [])
            r.save(run / "rounds/r01-complete.json", {"status": "generated"})
            with patch.object(r, "RUN", run), patch.object(r, "call") as invoke:
                r.generate(1, run / "baseline.json", True)
                invoke.assert_not_called()

    def test_cap_rejects_before_api(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "rounds").mkdir(); (run / "jobs").mkdir()
            text = "Title\n\nThis is the original body."
            r.save(run / "baseline.json", {"id": "base", "text": text, "sha256": r.sha(text)})
            (run / "source.txt").write_text(text)
            r.save(run / "claims.json", [])
            r.save(run / "jobs/r00-c001.json", {})
            with patch.object(r, "RUN", run), patch.object(r, "MAX_UNIQUE", 1), patch.object(r, "call") as invoke:
                with self.assertRaises(RuntimeError):
                    r.generate(1, run / "baseline.json", True)
                invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
