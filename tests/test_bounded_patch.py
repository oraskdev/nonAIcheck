import copy
import json
import time
import unittest
from unittest.mock import patch

from app import bounded_patch as editing
from app import pipeline, providers


class BoundedPatchTests(unittest.TestCase):
    def setUp(self):
        self.source = [{"id": "title", "type": "heading", "text": "A personal plan"},
            {"id": "p1", "type": "paragraph", "text":
             "I want to begin the garden with a few pots rather than fill the whole balcony at once. "
             "The balcony gets 4 hours of sunlight, which may suit the herbs I have in mind. "
             "I already own a small watering can, so I do not expect to buy another. "
             "If I travel during the summer, a friend could water the plants while I am away. "
             "I have not asked anyone yet. Before I spend more money, I will review how the first pots are doing "
             "and decide whether I have enough time to care for more plants."}]
        self.bank = {"atoms": [{"id": "a1", "statement": b["text"], "source_ids": [b["id"]]}
                               for b in self.source], "patches": [{"id": "edit1", "block_id": "p1",
            "find": "I want to begin the garden with a few pots rather than fill the whole balcony at once.",
            "replace": "I want to start with a few pots, leaving the rest of the balcony for later."}]}
        self.bank["atoms"][1]["id"] = "a2"
        self.candidate = editing.apply_patches(self.source, self.bank["patches"])
        self.options = {"writing_workflow": editing.VERSION, "detector": True, "detector_provider": "local"}

    def verdict(self, candidate=None, **changes):
        return {"source_sha256": editing.digest(self.source),
            "candidate_sha256": editing.digest(candidate or self.candidate),
            "inventory_complete_and_supported": True, "checked_atom_ids": ["a1", "a2"],
            "faithful": True, "issues": [], "repairs": [], **changes}

    def run_case(self, reviews=None, scores=(.9, .2)):
        outputs = [self.bank, self.bank, *(reviews or [self.verdict()])]
        history = []
        with patch("app.bounded_patch.providers.invoke", side_effect=[(json.dumps(o), {"input_tokens": 100, "output_tokens": 100}) for o in outputs]) as invoke, \
             patch("app.bounded_patch.providers.detect", side_effect=[{"status": "assessed", "ai_score": s} for s in scores]):
            result, report = editing.run(self.source, self.options, lambda *_: None,
                                        recorder=lambda kind, value: history.append((kind, copy.deepcopy(value))))
        return result, report, invoke, history

    def test_lower_score_requires_complete_hash_bound_source_review(self):
        for verdict in [self.verdict(issues=["A causal relationship is missing."], faithful=False),
                        self.verdict(candidate_sha256="wrong"),
                        self.verdict(checked_atom_ids=["a1"]),
                        self.verdict(inventory_complete_and_supported=False)]:
            with self.subTest(verdict=verdict):
                result, report, invoke, _ = self.run_case([verdict])
                self.assertEqual(result, self.source)
                self.assertEqual(report["after_detector"]["ai_score"], .9)
                self.assertFalse(report["detector_comparison"]["improved"])
                self.assertEqual(invoke.call_count, 3)

    def test_selected_candidate_is_exact_reviewed_and_measured_text(self):
        result, report, invoke, history = self.run_case()
        self.assertEqual(result, self.candidate)
        self.assertEqual(report["after_detector"]["ai_score"], .2)
        self.assertEqual([c.args[0] for c in invoke.call_args_list], ["anthropic", "openai", "xai"])
        self.assertTrue(all(c.kwargs["max_attempts"] == 1 for c in invoke.call_args_list))
        self.assertTrue(all(c.kwargs["max_output_tokens"] == 4000 for c in invoke.call_args_list))
        self.assertEqual([v["text_sha256"] for k, v in history if k == "assessment"][-1], editing.digest(result))

    def test_source_verbatim_repair_requires_new_review_and_own_measurement(self):
        find = self.candidate[1]["text"].split(". ", 1)[0] + "."
        replace = self.source[1]["text"].split(". ", 1)[0] + "."
        rejected = self.verdict(faithful=False, issues=["The revised opening overstates the intention to add pots later."],
            repairs=[{"block_id": "p1", "find": find, "replace": replace, "source_block_id": "p1"}])
        approved = self.verdict(self.source)
        result, report, invoke, history = self.run_case([rejected, approved], (.9, .2, .9))
        self.assertEqual(result, self.source)
        self.assertEqual(invoke.call_count, 4)
        self.assertEqual(report["after_detector"]["ai_score"], .9)
        self.assertEqual(report["detector_comparison"]["attempts"][-1]["version"], "source_repair")

    def test_invented_repair_is_rejected_before_a_fourth_call(self):
        rejected = self.verdict(faithful=False, issues=["Missing detail"], repairs=[{
            "block_id": "p1", "find": self.bank["patches"][0]["replace"],
            "replace": "I planted tomatoes last weekend.", "source_block_id": "p1"}])
        result, _, invoke, _ = self.run_case([rejected])
        self.assertEqual(result, self.source)
        self.assertEqual(invoke.call_count, 3)

    def test_repair_can_restore_source_modal_without_loosening_proposal_guard(self):
        bad = [{**b, "text": b["text"].replace("could water", "water")} for b in self.source]
        repair = {"block_id": "p1", "find": "a friend water the plants", "replace": "a friend could water the plants", "source_block_id": "p1"}
        fixed = editing.source_backed_repair(self.source, bad, {"issues": ["Lost uncertainty"], "repairs": [repair]})
        self.assertEqual(fixed, self.source)
        with self.assertRaises(ValueError):
            editing.apply_patches(bad, [repair])

    def test_ambiguous_overlapping_hidden_and_numeric_changes_fail(self):
        base = self.bank["patches"][0]
        for edits in [[base, base], [{**base, "find": "4 hours of sunlight", "replace": "8 hours of sunlight"}],
                      [{**base, "replace": "I want to start\u200b with pots."}],
                      [{**base, "block_id": "title", "find": "A personal plan", "replace": "New plan"}]]:
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                editing.apply_patches(self.source, edits)

    def test_cost_reservation_retained_when_provider_usage_is_unknown(self):
        budget = editing.CallBudget(.1, time.monotonic() + 60, lambda *_: None)
        with patch("app.bounded_patch.providers.invoke", return_value=("{}", {})):
            budget.call("openai", "Return JSON", {}, {})
        self.assertEqual(budget.cost, budget.usage[0]["reserved_usd"])
        self.assertEqual(budget.usage[0]["status"], "completed_usage_unknown")
        budget.limit = budget.cost
        with patch("app.bounded_patch.providers.invoke") as invoke, self.assertRaises(editing.LimitReached):
            budget.call("xai", "Return JSON", {}, {})
        invoke.assert_not_called()

    def test_immutable_heading_is_added_verbatim_without_inventing_a_source_fact(self):
        bank = copy.deepcopy(self.bank)
        bank["atoms"] = bank["atoms"][1:]
        validated = editing.validate_bank(bank, self.source)
        self.assertEqual(validated["atoms"][-1]["statement"], self.source[0]["text"])
        self.assertEqual(validated["atoms"][-1]["source_ids"], ["title"])

    def test_missing_detector_prevents_any_provider_spend(self):
        with patch("app.bounded_patch.providers.invoke") as invoke, \
             patch("app.bounded_patch.providers.detect", return_value={"status": "not_assessed"}), \
             self.assertRaises(providers.ProviderError):
            editing.run(self.source, self.options, lambda *_: None)
        invoke.assert_not_called()

    def test_old_quote_does_not_enter_new_workflow(self):
        with patch("app.bounded_patch.run") as bounded, \
             patch("app.pipeline.providers.refine", return_value=(self.source, {})):
            pipeline.run(self.source, {"detector": False}, lambda *_: None)
        bounded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
