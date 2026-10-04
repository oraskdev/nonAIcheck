"""Contracts for a fresh source-reviewed starting draft, before the unseen live test."""
import json
import unittest
from unittest.mock import patch

from app import bounded_draft, bounded_patch


class FreshDraftTests(unittest.TestCase):
    def setUp(self):
        self.source = [{"id": "title", "type": "heading", "text": "A weekly planning note"},
            {"id": "body", "type": "paragraph", "text":
             "I intend to set aside 30 minutes on Monday to review my responsibilities for the week. "
             "The aim is to choose a few realistic priorities, not to schedule every hour in advance. "
             "Some tasks may depend on information from other people. I have not asked them for updates yet. "
             "If their replies arrive late, I will review the order of the tasks rather than assume the original plan still works. "
             "I would like to try this routine for a month before deciding whether to continue. "
             "It should leave enough room for unexpected requests and time with my family."}]
        self.draft_text = (
            "On Monday I intend to give the coming week 30 minutes of planning. I want a few realistic priorities, "
            "not an advance schedule for every hour. Some tasks may need information from other people, whom "
            "I have yet to ask for updates. If replies arrive late, I will reconsider the task order instead of "
            "assuming my first plan still works. I would like to try the routine for a month before deciding "
            "whether to keep it. It should allow time for my family and unexpected requests.")
        self.first = {"atoms": [{"id": "a1", "statement": self.source[1]["text"], "source_ids": ["body"]}],
                      "paragraphs": [{"text": self.draft_text, "atom_ids": ["a1"]}]}
        self.draft = [self.source[0], {"id": "bounded-draft-p000", "type": "paragraph", "text": self.draft_text}]
        self.edit = {"id": "p1", "block_id": "bounded-draft-p000", "find": "I want a few realistic priorities",
                     "replace": "A few realistic priorities are what I want"}
        self.candidate = bounded_patch.apply_patches(self.draft, [self.edit])
        self.options = {"writing_workflow": bounded_draft.VERSION, "detector": True, "detector_provider": "local"}

    def review(self, candidate, **extra):
        return {"source_sha256": bounded_patch.digest(self.source), "candidate_sha256": bounded_patch.digest(candidate),
            "inventory_complete_and_supported": True, "checked_atom_ids": ["a1", "fixed_heading"],
            "faithful": True, "issues": [], "repairs": [], **extra}

    def execute(self, first=None, second=None, final=None, scores=(.9, .6, .4)):
        outputs = [first or self.first, second or self.review(self.draft, patches=[self.edit]),
                   final or self.review(self.candidate)]
        with patch("app.bounded_patch.providers.invoke", side_effect=[(json.dumps(o), {"input_tokens": 10, "output_tokens": 10}) for o in outputs]) as invoke, \
             patch("app.bounded_patch.providers.detect", side_effect=[{"status": "assessed", "ai_score": s} for s in scores]) as detect:
            result, report = bounded_patch.run(self.source, self.options, lambda *_: None)
        return result, report, invoke, detect

    def test_fresh_draft_is_source_reviewed_before_patch_search_and_final_review(self):
        result, report, invoke, detect = self.execute()
        self.assertEqual(result, self.candidate)
        self.assertEqual(report["writing_method"], bounded_draft.VERSION)
        self.assertTrue(report["structure_recomposed"])
        self.assertEqual([c.args[0] for c in invoke.call_args_list], ["anthropic", "openai", "xai"])
        self.assertEqual([c.args[0] for c in detect.call_args_list], [bounded_patch.content(self.source),
                         bounded_patch.content(self.draft), bounded_patch.content(self.candidate)])
        second_input = json.loads(invoke.call_args_list[1].args[2])
        self.assertEqual(second_input["source"], self.source)
        self.assertEqual(second_input["candidate"], self.draft)
        self.assertEqual(report["initialization"]["status"], "accepted")

    def test_unapproved_seed_cannot_be_scored_or_have_a_patch_bank_applied(self):
        for changes in [{"faithful": False, "issues": ["An intention became a completed action."]},
                        {"candidate_sha256": "incorrect"}, {"inventory_complete_and_supported": False}]:
            with self.subTest(changes=changes):
                seed_review = self.review(self.draft, patches=[self.edit], **changes)
                result, report, invoke, detect = self.execute(second=seed_review,
                    final=self.review(self.source), scores=(.9,))
                self.assertEqual(result, self.source)
                self.assertEqual(detect.call_count, 1)
                self.assertEqual(invoke.call_count, 3)
                self.assertEqual(report["initialization"]["status"], "rejected")

    def test_seed_cannot_change_a_protected_number(self):
        first = {**self.first, "paragraphs": [{"text": self.draft_text.replace("30", "45"), "atom_ids": ["a1"]}]}
        with patch("app.bounded_patch.providers.invoke", return_value=(json.dumps(first), {"input_tokens": 10, "output_tokens": 10})) as invoke, \
             patch("app.bounded_patch.providers.detect", return_value={"status": "assessed", "ai_score": .9}), \
             self.assertRaises(bounded_patch.providers.ProviderError):
            bounded_patch.run(self.source, self.options, lambda *_: None)
        self.assertEqual(invoke.call_count, 1)

    def test_lower_scoring_seed_does_not_escape_a_failed_final_review(self):
        result, report, _, _ = self.execute(final=self.review(self.candidate, faithful=False,
            issues=["The final wording lost a qualification."]))
        self.assertEqual(result, self.source)
        self.assertEqual(report["after_detector"]["ai_score"], .9)

    def test_selected_source_keeps_original_structure_metadata(self):
        result, report, _, _ = self.execute(final=self.review(self.source), scores=(.1, .6, .4))
        self.assertEqual(result, self.source)
        self.assertFalse(report["structure_recomposed"])

    def test_heading_in_middle_requires_established_layout_workflow(self):
        source = [self.source[1], self.source[0], {**self.source[1], "id": "body2"}]
        with patch("app.bounded_patch.providers.invoke") as invoke, self.assertRaises(bounded_patch.providers.ProviderError):
            bounded_patch.run(source, self.options, lambda *_: None)
        invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
