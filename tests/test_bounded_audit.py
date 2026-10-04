"""Regression coverage for provider contracts, accounting and failure handling."""
import copy
import json
import time
import unittest
from unittest.mock import MagicMock, patch

import httpx

from app import bounded_draft, bounded_patch as editing
from app import providers


class BoundedAuditTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.budget = editing.CallBudget(.45, time.monotonic() + 300,
            lambda kind, value: self.events.append((kind, copy.deepcopy(value))))

    @staticmethod
    def response(usage, output="{}"):
        return {"status": "completed", "output": [{"content": [
            {"type": "output_text", "text": output}]}], "usage": usage}

    def test_review_schema_reaches_both_responses_providers(self):
        for provider in ("openai", "xai"):
            with self.subTest(provider=provider), patch("app.providers._request",
                    return_value=self.response({"input_tokens": 10, "output_tokens": 10})) as request:
                self.budget.call(provider, "Return a complete review.", {}, editing.REVIEW_SCHEMA)
                wire_payload = json.dumps(request.call_args.args[2])
                for required in editing.REVIEW_SCHEMA["required"]:
                    self.assertIn(required, wire_payload)

    def test_partial_usage_retains_reservation_and_explicit_unknown_status(self):
        for usage in ({"input_tokens": 150}, {"output_tokens": 100}, {}):
            with self.subTest(usage=usage), patch("app.providers._request",
                    return_value=self.response(usage)):
                self.budget.call("openai", "Return JSON.", {}, {})
                record = self.budget.usage[-1]
                self.assertEqual(record["status"], "completed_usage_unknown")
                self.assertEqual(record["charged_or_reserved_usd"], record["reserved_usd"])
        self.assertEqual(self.budget.cost,
                         sum(record["reserved_usd"] for record in self.budget.usage))

    def test_complete_usage_releases_reservation_and_keeps_raw_response(self):
        raw = '{"accepted": true}'
        usage = {"input_tokens": 150, "output_tokens": 100}
        with patch("app.providers._request", return_value=self.response(usage, raw)):
            self.assertEqual(self.budget.call("openai", "Return JSON.", {}, {}), {"accepted": True})
        record = self.budget.usage[-1]
        self.assertEqual(record["status"], "completed")
        self.assertAlmostEqual(record["charged_or_reserved_usd"], .0013)
        receipt = next(value for kind, value in self.events if kind == "provider_completed")
        self.assertEqual(receipt["raw_output"], raw)
        self.assertEqual(receipt["usage"], usage)

    def test_network_timeout_has_one_attempt_and_retains_its_reservation(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.side_effect = httpx.ReadTimeout("Simulated timeout")
        with patch("app.providers.httpx.Client", return_value=client) as factory, \
             patch("app.providers.time.sleep") as sleep, \
             self.assertRaises(providers.ProviderError):
            self.budget.call("openai", "Return JSON.", {}, {})
        client.post.assert_called_once()
        sleep.assert_not_called()
        self.assertLessEqual(factory.call_args.kwargs["timeout"].read, 60)
        self.assertEqual(client.post.call_args.kwargs["json"]["max_output_tokens"], 4000)
        self.assertEqual(self.budget.cost, self.budget.usage[0]["reserved_usd"])
        self.assertNotIn(self.budget.usage[0]["status"], ("completed", "completed_usage_unknown"))
        self.assertFalse(any(kind == "provider_completed" for kind, _ in self.events))

    def test_provider_failure_escapes_pipeline_for_worker_refund(self):
        source = [{"id": "p1", "type": "paragraph", "text": " ".join(["A clear source sentence."] * 24)}]
        options = {"writing_workflow": editing.VERSION, "detector": True, "detector_provider": "local"}
        with patch("app.bounded_patch.providers.detect", return_value={"status": "assessed", "ai_score": .9}), \
             patch("app.bounded_patch.providers.invoke", side_effect=providers.ProviderError("Provider unavailable")), \
             self.assertRaises(providers.ProviderError):
            editing.run(source, options, lambda *_: None)

    def test_fifth_request_is_rejected_before_transmission(self):
        with patch("app.bounded_patch.providers.invoke", return_value=("{}", {"input_tokens": 1, "output_tokens": 1})) as invoke:
            for _ in range(4):
                self.budget.call("openai", "Return JSON.", {}, {})
            with self.assertRaises(editing.LimitReached):
                self.budget.call("openai", "Return JSON.", {}, {})
        self.assertEqual(invoke.call_count, 4)

    def test_fresh_cleanup_seed_variants_and_repair_share_fourteen_assessment_cap(self):
        names = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
                 "india", "juliet", "kilo", "lima")
        original_sentences = [f"I plan to review the {name} section before making any changes to it." for name in names]
        source = [{"id": "title", "type": "heading", "text": "A document review plan"},
                  {"id": "body", "type": "paragraph", "text": " ".join(original_sentences)}]
        raw = copy.deepcopy(source)
        raw[1]["text"] = raw[1]["text"].replace("alpha", "al\u00adpha")
        seed_sentences = [sentence.replace("I plan", "I intend") for sentence in original_sentences]
        seed = [source[0], {"id": "bounded-draft-p000", "type": "paragraph", "text": " ".join(seed_sentences)}]
        patches = [{"id": f"p{i}", "block_id": seed[1]["id"], "find": sentence,
                    "replace": sentence.replace("review", "take a look at")}
                   for i, sentence in enumerate(seed_sentences)]
        inputs = []

        def approved(payload):
            return {"source_sha256": payload["source_sha256"],
                    "candidate_sha256": payload["candidate_sha256"],
                    "inventory_complete_and_supported": True,
                    "checked_atom_ids": ["a1", "fixed_heading"],
                    "faithful": True, "issues": [], "repairs": []}

        def invoke(provider, system, prompt, **kwargs):
            payload = json.loads(prompt)
            inputs.append((provider, payload))
            if provider == "anthropic":
                value = {"atoms": [{"id": "a1", "statement": source[1]["text"], "source_ids": ["body"]}],
                         "paragraphs": [{"text": seed[1]["text"], "atom_ids": ["a1"]}]}
            elif provider == "openai":
                value = {**approved(payload), "patches": patches}
            elif len(inputs) == 3:
                value = {**approved(payload), "faithful": False, "issues": ["Restore the source's opening wording."],
                         "repairs": [{"block_id": seed[1]["id"],
                                      "find": payload["candidate"][1]["text"].split(". ")[0] + ".",
                                      "replace": original_sentences[0], "source_block_id": "body"}]}
            else:
                value = approved(payload)
            return json.dumps(value), {"input_tokens": 10, "output_tokens": 10}

        scores = [.99, .98, .9, *[.8 - i * .01 for i in range(10)], .65]
        options = {"writing_workflow": bounded_draft.VERSION, "detector": True, "detector_provider": "local"}
        with patch("app.bounded_patch.providers.invoke", side_effect=invoke) as api, \
             patch("app.bounded_patch.providers.detect", side_effect=[
                 {"status": "assessed", "ai_score": score} for score in scores]) as detect:
            result, report = editing.run(raw, options, lambda *_: None)
        self.assertEqual(api.call_count, 4)
        self.assertEqual(detect.call_count, 14)
        self.assertTrue(report["structure_recomposed"])
        self.assertEqual(report["detector_comparison"]["selected_version"], "source_repair")
        self.assertEqual(report["after_detector"]["ai_score"], .65)
        self.assertEqual(report["detector_comparison"]["attempts"][-1]["text_sha256"], editing.digest(result))
        for provider, payload in inputs[1:]:
            self.assertEqual(payload["source"], source)
            self.assertEqual(payload["source_sha256"], editing.digest(source))
        self.assertEqual(inputs[-1][1]["candidate_sha256"], editing.digest(result))
        self.assertEqual(detect.call_args_list[-1].args[0], editing.content(result))

    def test_new_draft_version_does_not_change_pipeline_dispatch(self):
        from app import pipeline
        source = [{"id": "p1", "type": "paragraph", "text": "A short source."}]
        with patch("app.bounded_patch.run") as experimental, \
             patch("app.pipeline.providers.refine", return_value=(source, {})) as legacy:
            result, _ = pipeline.run(source, {"writing_workflow": bounded_draft.VERSION, "detector": False}, lambda *_: None)
        self.assertEqual(result, source)
        legacy.assert_called_once()
        experimental.assert_not_called()

    def test_heading_only_document_is_rejected_before_any_provider_or_detector_call(self):
        source = [{"id": "heading", "type": "heading", "text": " ".join(["An unusually long title"] * 24)}]
        options = {"writing_workflow": bounded_draft.VERSION, "detector": True, "detector_provider": "local"}
        with patch("app.bounded_patch.providers.invoke") as invoke, \
             patch("app.bounded_patch.providers.detect") as detect, \
             self.assertRaises(providers.ProviderError):
            editing.run(source, options, lambda *_: None)
        invoke.assert_not_called()
        detect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
