"""Offline phase-B activation and reviewer-evidence binding checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.research import phase_b as b
from scripts.research import recovery as r


class PhaseBSafety(unittest.TestCase):
    def test_activation_needs_explicit_approval(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(b, "B", Path(directory)):
            with self.assertRaisesRegex(RuntimeError, "coordinator authorization"):
                b.generate()

    def test_overlap_or_changed_span_is_not_combined(self):
        text = "abcdefghij"
        p1 = {"start": 1, "end": 4, "find": "bcd", "replace": "FIRST"}
        p2 = {"start": 3, "end": 6, "find": "def", "replace": "SECOND"}
        self.assertIsNone(b.apply(text, [p1, p2]))
        with self.assertRaisesRegex(ValueError, "span identity"):
            b.apply(text, [{**p1, "find": "xxx"}])

    def test_approved_id_cannot_transfer_to_different_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            source = "Garden note\n\nThese herbs may need water every morning."
            claims = [{"id": f"G{i:02d}", "statement": "Source claim"} for i in range(1, 33)]
            parent = {"id": "parent", "text": source, "sha256": r.sha(source), "source_sha256": r.sha(source)}
            p = r.valid_patch(source, {"id": "p1", "find": "These herbs may need water every morning.",
                                      "replace": "These herbs may need watering each morning."})
            review = {"baseline_faithful": True, "baseline_issues": [], "checked_claim_ids": [c["id"] for c in claims],
                      "patches": [{"id": "p1", "faithful": True, "issues": []}]}
            r.save(run / "rounds/r08-bank.json", {"parent": parent, "patches": [p]})
            r.save(run / "rounds/r08-review.json", review)
            r.save(run / "rounds/r08-grok.request.json", {"provider": "xai", "model": r.MODELS["xai"],
                "prompt": json.dumps({"source": source, "current": source, "claims": claims, "patches": [p]})})
            r.save(run / "rounds/r08-grok.response.json", {"http_status": 200, "body": {"status": "completed",
                "output": [{"content": [{"type": "output_text", "text": json.dumps(review)}]}]}})
            with patch.object(r, "RUN", run), patch.object(r, "bound_source", return_value=(source, claims)), \
                 patch.object(r, "parent_approvals", return_value=["reviewer1", "reviewer2"]), \
                 patch.object(b, "score_pair", return_value=[.2, .1]):
                b.bank_ranked("r08")
                altered = {**p, "replace": "These herbs may need a drink every morning."}
                r.save(run / "rounds/r08-bank.json", {"parent": parent, "patches": [altered]})
                with self.assertRaisesRegex(ValueError, "no longer valid or approved"):
                    b.bank_ranked("r08")


if __name__ == "__main__":
    unittest.main()
