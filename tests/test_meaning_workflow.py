import json
import unittest
from unittest.mock import patch

from app import providers


class MeaningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = [
            {"id": "title", "type": "paragraph", "text": "My plan"},
            {"id": "body", "type": "paragraph", "text": "I may try the new routine for 30 minutes each morning, but I have not decided whether it will help."},
        ]
        self.draft = [self.source[0], {**self.source[1], "text": "Will this help? I have not decided yet. I may give the new routine 30 minutes each morning."}]

    def test_empty_review_preserves_draft_verbatim(self):
        result, flags = providers.apply_fidelity_review('{"corrections":[]}', self.source, self.draft)
        self.assertEqual(result, self.draft)
        self.assertEqual(flags, [])

    def test_fenced_json_is_accepted_without_extra_prose(self):
        self.assertEqual(providers.json_output('```json\n{"corrections":[]}\n```'), {"corrections": []})
        with self.assertRaises(ValueError):
            providers.json_output('Here is your result: {"corrections":[]}')

    def test_review_cannot_change_protected_number(self):
        review = {"corrections": [{"id": "body", "text": self.draft[1]["text"].replace("30", "45"), "reason": "An incorrect correction"}]}
        result, flags = providers.apply_fidelity_review(json.dumps(review), self.source, self.draft)
        self.assertEqual(result[1], self.source[1])
        self.assertEqual(len(flags), 2)

    def test_review_rejects_unknown_and_duplicate_ids(self):
        correction = {"id": "body", "text": self.draft[1]["text"], "reason": "Missing qualification"}
        for corrections in [[{**correction, "id": "absent"}], [correction, correction]]:
            with self.assertRaises(providers.ProviderError):
                providers.apply_fidelity_review(json.dumps({"corrections": corrections}), self.source, self.draft)

    def test_incomplete_plan_fails_before_paid_drafting(self):
        with patch("app.providers.invoke", return_value=('{"blocks":[]}', {})) as invoke:
            with self.assertRaises(providers.ProviderError):
                providers.refine(self.source, {"detector": True}, lambda *_: None)
        self.assertEqual(invoke.call_count, 1)

    def test_all_providers_used_and_title_kept_in_independent_revisions(self):
        plan = {"blocks": [{"id": b["id"], "points": [b["text"]]} for b in self.source]}
        changed_title = [{**self.draft[0], "text": "A different title"}, self.draft[1]]
        for alternate, order in [(False, ["anthropic", "openai", "xai"]), (True, ["openai", "anthropic", "xai"])]:
            outputs = [(json.dumps(plan), {}), (json.dumps({"blocks": changed_title}), {}), ('{"corrections":[]}', {})]
            with patch("app.providers.invoke", side_effect=outputs) as invoke:
                result, report = providers.refine(self.source, {"detector": True, "alternate_revision": alternate}, lambda *_: None,
                                                   initial=[{**self.source[0], "text": "Prior draft must not be used"}])
            self.assertEqual([c.args[0] for c in invoke.call_args_list], order)
            self.assertEqual(result[0], self.source[0])
            self.assertEqual(result[1], self.draft[1])
            self.assertNotIn("Prior draft", invoke.call_args_list[0].args[2])
            self.assertEqual(report["writing_method"], "meaning-first-v1")


if __name__ == "__main__":
    unittest.main()
