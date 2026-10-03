import copy
import json
import unittest
from unittest.mock import patch

from app import providers


class RecompositionTests(unittest.TestCase):
    def setUp(self):
        self.source = [
            {"id": "title", "type": "heading", "text": "A weekly plan"},
            {"id": "first", "type": "paragraph", "text":
             "I want to start each week by considering the responsibilities that need my attention and those that can wait. "
             "I intend to choose a few realistic priorities rather than a long list of ambitions. Before messages each morning, "
             "I will spend 30 minutes on one important task. I do not expect to finish it in one sitting. I want to begin "
             "the work that needs concentration before responding to other people's requests."},
            {"id": "second", "type": "paragraph", "text":
             "On 12 October, I will review which tasks received enough attention and whether my time estimates were realistic. "
             "I will also check whether the morning session was practical. That review should guide the following week's plan. "
             "I want room for unexpected requests and ordinary life. If an afternoon is disrupted, I do not want to treat "
             "the whole week as a failure. A notebook and brief review would suit me if they provide enough structure."},
        ]
        self.plan = {"genre": "personal planning note", "voice": "first-person intentions, tentative benefits",
                     "atoms": [{"id": "a1", "statement": self.source[1]["text"], "source_ids": ["first"]},
                               {"id": "a2", "statement": self.source[2]["text"], "source_ids": ["second"]}]}
        self.paragraphs = [
            {"text": "On 12 October, I'll review which tasks got enough attention, whether my estimates were realistic "
                     "and whether the morning session was practical. The answers should guide the next week's plan.", "atom_ids": ["a2"]},
            {"text": "Before messages, I'll give one important task 30 minutes each morning. I only need to start, "
                     "not finish in one sitting. At the start of the week I'll choose a few realistic priorities, "
                     "separating the responsibilities that need me from those that can wait.", "atom_ids": ["a1"]},
            {"text": "There needs to be room for unexpected requests and ordinary life. A disrupted afternoon shouldn't "
                     "mean a failed week. I'd prefer a notebook and short review if they provide enough structure.", "atom_ids": ["a2"]},
        ]
        self.review = {"corrections": [], "unresolved_issues": [], "checked_atom_ids": ["a1", "a2"], "faithful": True}

    def run_case(self, paragraphs=None, review=None, alternate=False):
        outputs = [self.plan, {"paragraphs": paragraphs if paragraphs is not None else self.paragraphs},
                   self.review if review is None else review]
        with patch("app.providers.invoke", side_effect=[(json.dumps(item), {}) for item in outputs]) as invoke:
            result, report = providers.refine(self.source, {"detector": True, "alternate_revision": alternate}, lambda *_: None,
                                               initial=[{"id": "irrelevant", "text": "Previous draft must not be reused"}])
        return result, report, invoke

    def test_whole_section_reorders_and_splits_with_exact_global_values(self):
        for alternate, order in [(False, ["anthropic", "openai", "xai"]), (True, ["openai", "anthropic", "xai"])]:
            with self.subTest(alternate=alternate):
                result, report, invoke = self.run_case(alternate=alternate)
                self.assertEqual(result[0], self.source[0])
                self.assertEqual(len(result), 4)
                self.assertEqual([b["text"] for b in result[1:]], [p["text"] for p in self.paragraphs])
                self.assertEqual([c.args[0] for c in invoke.call_args_list], order)
                self.assertEqual([c.kwargs["response_schema"] for c in invoke.call_args_list],
                                 [providers.RECOMPOSITION_PLAN_SCHEMA, providers.RECOMPOSITION_DRAFT_SCHEMA,
                                  providers.RECOMPOSITION_REVIEW_SCHEMA])
                self.assertNotIn("Previous draft", invoke.call_args_list[0].args[2])
                self.assertEqual(report["writing_method"], "meaning-first-v2")
                self.assertTrue(report["structure_recomposed"])
                self.assertEqual(report["recompose_runs"][0]["status"], "accepted")
                self.assertEqual(report["recompose_runs"][0]["output_blocks"], 3)
                self.assertTrue(set(b["id"] for b in result[1:]).isdisjoint(b["id"] for b in self.source))
                self.assertEqual(providers.protected_tokens(" ".join(b["text"] for b in result)),
                                 providers.protected_tokens(" ".join(b["text"] for b in self.source)))

    def test_protected_value_drift_rejects_entire_run_after_all_three_providers(self):
        paragraphs = copy.deepcopy(self.paragraphs)
        paragraphs[1]["text"] = paragraphs[1]["text"].replace("30", "45")
        result, report, invoke = self.run_case(paragraphs=paragraphs)
        self.assertEqual(result, self.source)
        self.assertFalse(report["structure_recomposed"])
        self.assertEqual(report["recompose_runs"][0]["reason"], "protected_values_changed")
        self.assertEqual(invoke.call_count, 3)
        self.assertIn("Kept this source section", report["flags"][-1]["message"])

    def test_minimal_source_patch_is_applied_before_protected_value_check(self):
        paragraphs = copy.deepcopy(self.paragraphs)
        paragraphs[1]["text"] = paragraphs[1]["text"].replace("30", "45")
        review = {**self.review, "corrections": [{"id": "recompose-0001-p001", "find": "45", "replace": "30",
                                                 "reason": "The original specifies 30 minutes."}]}
        result, report, _ = self.run_case(paragraphs=paragraphs, review=review)
        self.assertEqual(result[2]["text"], self.paragraphs[1]["text"])
        self.assertEqual(report["recompose_runs"][0]["status"], "accepted")
        self.assertEqual(len(report["flags"]), 1)

    def test_minimal_patch_capitalization_respects_sentence_boundaries(self):
        plan = {"atoms": [{"id": "a1"}]}
        cases = [
            ("I should review the plan.", "We should review the plan."),
            ("This may help. I should review the plan.", "This may help. We should review the plan."),
            ("Will this help? I should review the plan.", "Will this help? We should review the plan."),
            ('The note says “Review it.” I should review the plan.', 'The note says “Review it.” We should review the plan.'),
            ("If it helps, I should review the plan.", "If it helps, we should review the plan."),
        ]
        for draft_text, expected in cases:
            with self.subTest(draft_text=draft_text):
                draft = [{"id": "p", "type": "paragraph", "text": draft_text}]
                review = {"corrections": [{"id": "p", "find": "I should", "replace": "we should",
                                          "reason": "The source refers to the team."}],
                          "checked_atom_ids": ["a1"], "unresolved_issues": [], "faithful": True}
                result, _, failure = providers.review_recomposition(json.dumps(review), draft, draft, plan)
                self.assertIsNone(failure)
                self.assertEqual(result[0]["text"], expected)

    def test_patch_capitalization_does_not_alter_mixed_case_name(self):
        draft = [{"id": "p", "type": "paragraph", "text": "The shop may publish the listing."}]
        review = {"corrections": [{"id": "p", "find": "The shop", "replace": "eBay", "reason": "Restore the source name."}],
                  "checked_atom_ids": ["a1"], "unresolved_issues": [], "faithful": True}
        result, _, failure = providers.review_recomposition(json.dumps(review), draft, draft, {"atoms": [{"id": "a1"}]})
        self.assertIsNone(failure)
        self.assertEqual(result[0]["text"], "eBay may publish the listing.")

    def test_unresolved_or_incomplete_semantic_reviews_restore_source(self):
        cases = [
            ({**self.review, "unresolved_issues": ["The draft changes an intention into an accomplished action."], "faithful": False},
             "unresolved_source_discrepancy"),
            ({**self.review, "faithful": False}, "unresolved_source_discrepancy"),
            ({**self.review, "checked_atom_ids": ["a1"]}, "invalid_source_review"),
            ({"corrections": []}, "invalid_source_review"),
            ({**self.review, "faithful": "true"}, "invalid_source_review"),
            ({**self.review, "checked_atom_ids": ["a1", "a2", "a2"]}, "invalid_source_review"),
        ]
        for review, reason in cases:
            with self.subTest(reason=reason, review=review):
                result, report, _ = self.run_case(review=review)
                self.assertEqual(result, self.source)
                self.assertEqual(report["recompose_runs"][0]["reason"], reason)
                self.assertFalse(report["structure_recomposed"])

    def test_ambiguous_or_unrecognized_span_corrections_are_not_applied(self):
        for find, block_id in [("the", "recompose-0001-p001"), ("missing words", "recompose-0001-p001"),
                               ("30", "unknown")]:
            review = {**self.review, "corrections": [{"id": block_id, "find": find, "replace": "replacement",
                                                     "reason": "A discrepancy"}]}
            result, report, _ = self.run_case(review=review)
            self.assertEqual(result, self.source)
            self.assertEqual(report["recompose_runs"][0]["reason"], "invalid_source_review")

    def test_mapping_identifies_reordering_even_with_same_paragraph_count(self):
        paragraphs = [{"text": self.source[2]["text"], "atom_ids": ["a2"]},
                      {"text": self.source[1]["text"], "atom_ids": ["a1"]}]
        result, report, _ = self.run_case(paragraphs=paragraphs)
        self.assertEqual(len(result), len(self.source))
        self.assertTrue(report["structure_recomposed"])

    def test_unchanged_output_is_not_marked_recomposed(self):
        paragraphs = [{"text": b["text"], "atom_ids": [f"a{i}"]} for i, b in enumerate(self.source[1:], 1)]
        result, report, _ = self.run_case(paragraphs=paragraphs)
        self.assertEqual(result, self.source)
        self.assertFalse(report["structure_recomposed"])

    def test_shortened_or_invisible_modified_output_is_rejected(self):
        for paragraphs, reason in [
            ([{"text": "30 minutes before messages; review on 12 October.", "atom_ids": ["a1", "a2"]}], "excessive_shortening"),
            ([{**p, "text": p["text"] + "\u200b"} for p in self.paragraphs], "unexpected_format_characters"),
        ]:
            result, report, _ = self.run_case(paragraphs=paragraphs)
            self.assertEqual(result, self.source)
            self.assertEqual(report["recompose_runs"][0]["reason"], reason)

    def test_url_or_numeric_occurrence_changes_fail_global_guard(self):
        source = [{"text": "Read https://example.com/guide and allow 30 minutes. " * 4}]
        for text in [source[0]["text"].replace("example.com", "other.example"),
                     source[0]["text"] + " Allow 30 more minutes."]:
            self.assertEqual(providers.validate_recomposition(source, [{"text": text}]), "protected_values_changed")

    def test_numeric_sign_percent_and_attached_currency_are_protected_exactly(self):
        for before, after in [("-5", "5"), ("−5", "5"), ("﹣5", "5"), ("+5", "5"),
                              ("5%", "5"), ("5％", "5"), ("$60", "€60"), ("£60", "60"),
                              ("¥60", "60"), ("60₪", "60"), ("-$60.50", "$60.50"),
                              ("$-60.50", "$60.50"), ("-.5%", ".5%")]:
            with self.subTest(before=before, after=after):
                source = [{"text": f"The recorded value is {before}. Keep the proposed review unchanged."}]
                changed = [{"text": source[0]["text"].replace(before, after)}]
                self.assertEqual(providers.validate_recomposition(source, changed), "protected_values_changed")
                self.assertIsNone(providers.validate_recomposition(source, source))
        tokens = providers.protected_tokens("https://example.com/-5?q=6 [1, 2] -5% $60.50 12–15")
        self.assertEqual(dict(tokens), {"https://example.com/-5?q=6": 1, "[1, 2]": 1,
                                        "-5%": 1, "$60.50": 1, "12–15": 1})

    def test_rejected_run_does_not_report_patches_to_discarded_draft_ids(self):
        paragraphs = copy.deepcopy(self.paragraphs)
        paragraphs[0]["text"] = paragraphs[0]["text"].replace("12", "13")
        paragraphs[1]["text"] = paragraphs[1]["text"].replace("30", "45")
        review = {**self.review, "corrections": [{"id": "recompose-0001-p001", "find": "45", "replace": "30",
                                                 "reason": "The source specifies 30 minutes."}]}
        result, report, _ = self.run_case(paragraphs=paragraphs, review=review)
        self.assertEqual(result, self.source)
        self.assertEqual(report["recompose_runs"][0]["reason"], "protected_values_changed")
        self.assertEqual(len(report["flags"]), 1)
        self.assertEqual(report["flags"][0]["block_id"], "first")
        self.assertIn("Kept this source section", report["flags"][0]["message"])

    def test_incomplete_plan_or_draft_stops_before_further_paid_work(self):
        incomplete_plan = {**self.plan, "atoms": self.plan["atoms"][:1]}
        with patch("app.providers.invoke", return_value=(json.dumps(incomplete_plan), {})) as invoke:
            with self.assertRaises(providers.ProviderError):
                providers.refine(self.source, {"depth": "thorough"}, lambda *_: None)
        self.assertEqual(invoke.call_count, 1)
        with patch("app.providers.invoke", side_effect=[(json.dumps(self.plan), {}),
                                                        (json.dumps({"paragraphs": self.paragraphs[:1]}), {})]) as invoke:
            with self.assertRaises(providers.ProviderError):
                providers.refine(self.source, {"depth": "thorough"}, lambda *_: None)
        self.assertEqual(invoke.call_count, 2)

    def test_layout_rich_documents_and_short_prose_keep_existing_path(self):
        for anchor in [{"id": "table", "type": "table_row", "text": "Name | Value"},
                       {"id": "slide", "type": "paragraph", "text": "Slide body", "slide": 1},
                       {"id": "list", "type": "paragraph", "text": "- A bullet point"},
                       {"id": "nested-list", "type": "paragraph", "text": "Introductory prose.\n- An internal bullet"},
                       {"id": "numbered-list", "type": "paragraph", "text": "Introductory prose.\n1. An internal item"}]:
            self.assertIsNone(providers.recomposition_segments([*self.source, anchor]))
        self.assertIsNone(providers.recomposition_segments([{"id": "short", "type": "paragraph", "text": "A very short note."}]))
        with patch("app.providers._legacy_refine", return_value=(self.source, {})) as legacy:
            providers.refine(self.source, {"depth": "light", "detector": False}, lambda *_: None)
        self.assertEqual(legacy.call_count, 1)

    def test_runs_are_bounded_and_do_not_cross_fixed_anchors(self):
        body = "A meaningful sentence about the proposed task and its qualifications. " * 18
        heading = {"id": "anchor", "type": "heading", "text": "Another section"}
        blocks = [{"id": f"b{i}", "type": "paragraph", "text": body} for i in range(10)]
        blocks.insert(4, heading)
        segments = providers.recomposition_segments(blocks)
        self.assertEqual([b for _, section in segments for b in section], blocks)
        for kind, section in segments:
            if kind == "run":
                self.assertLessEqual(len("\n\n".join(b["text"] for b in section)), 6500)
                self.assertNotIn(heading, section)
        self.assertIn(("fixed", [heading]), segments)

    def test_one_rejected_run_does_not_discard_another_accepted_run_or_anchors(self):
        anchor = {"id": "second-heading", "type": "heading", "text": "A separate note"}
        later_source = [{**b, "id": b["id"] + "-later"} for b in self.source[1:]]
        later_plan = copy.deepcopy(self.plan)
        for atom in later_plan["atoms"]:
            atom["source_ids"] = [s + "-later" for s in atom["source_ids"]]
        later_review = {**self.review, "faithful": False, "unresolved_issues": ["A qualification is missing."]}
        outputs = [self.plan, {"paragraphs": self.paragraphs}, self.review,
                   later_plan, {"paragraphs": self.paragraphs}, later_review]
        progress = []
        with patch("app.providers.invoke", side_effect=[(json.dumps(item), {}) for item in outputs]) as invoke:
            result, report = providers.refine([*self.source, anchor, *later_source], {"depth": "thorough"},
                                               lambda percent, stage: progress.append(percent))
        self.assertEqual(invoke.call_count, 6)
        self.assertEqual(result[0], self.source[0])
        self.assertEqual([b["text"] for b in result[1:4]], [p["text"] for p in self.paragraphs])
        self.assertEqual(result[4], anchor)
        self.assertEqual(result[5:], later_source)
        self.assertTrue(report["structure_recomposed"])
        self.assertEqual([d["status"] for d in report["recompose_runs"]], ["accepted", "rejected"])
        self.assertEqual(progress, sorted(progress))


class ProviderPayloadTests(unittest.TestCase):
    def payload(self, provider, model, effort):
        response = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        with patch.object(providers.settings, provider + "_model", model), \
                patch.object(providers.settings, provider + "_reasoning_effort", effort, create=True), \
                patch("app.providers._request", return_value=response) as request:
            output, usage = providers.invoke(provider, "Return JSON.", "{}")
        self.assertEqual(output, "{}")
        return request.call_args.args[2]

    def test_modern_openai_uses_json_and_configured_reasoning(self):
        for model in ["gpt-6.1-sol", "gpt-5.4-mini"]:
            payload = self.payload("openai", model, "medium")
            self.assertEqual(payload["text"], {"format": {"type": "json_object"}})
            self.assertEqual(payload["reasoning"], {"effort": "medium"})
            self.assertIn("json", payload["input"].lower())
            self.assertTrue(payload["input"].endswith("{}"))
            self.assertFalse(payload["store"])

    def test_legacy_openai_omits_unsupported_reasoning(self):
        payload = self.payload("openai", "gpt-4.1-mini", "medium")
        self.assertEqual(payload["text"], {"format": {"type": "json_object"}})
        self.assertNotIn("reasoning", payload)
        self.assertIn("json", payload["input"].lower())

    def test_xai_uses_supported_configured_effort(self):
        payload = self.payload("xai", "grok-4.7", "low")
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertNotIn("text", payload)

    def test_anthropic_native_schema_is_sent_without_beta_or_prefill(self):
        response = {"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"paragraphs":[]}'}]}
        with patch("app.providers._request", return_value=response) as request:
            output, _ = providers.invoke("anthropic", "Return JSON.", "Input data.",
                                         response_schema=providers.RECOMPOSITION_DRAFT_SCHEMA)
        payload = request.call_args.args[2]
        self.assertEqual(payload["output_config"], {"format": {"type": "json_schema", "schema": providers.RECOMPOSITION_DRAFT_SCHEMA}})
        self.assertEqual([m["role"] for m in payload["messages"]], ["user"])
        self.assertNotIn("anthropic-beta", request.call_args.args[1])
        self.assertEqual(json.loads(output), {"paragraphs": []})

    def test_anthropic_still_rejects_refusal_or_truncated_native_output(self):
        for reason in ["refusal", "max_tokens"]:
            with patch("app.providers._request", return_value={"stop_reason": reason, "content": []}):
                with self.assertRaises(providers.ProviderError):
                    providers.invoke("anthropic", "Return JSON.", "Input data.",
                                     response_schema=providers.RECOMPOSITION_DRAFT_SCHEMA)

    def test_multiple_json_objects_are_still_rejected(self):
        with self.assertRaises(ValueError):
            providers.json_output('{"paragraphs":[]}\nWait, here is another version.\n{"paragraphs":[]}')


if __name__ == "__main__":
    unittest.main()
