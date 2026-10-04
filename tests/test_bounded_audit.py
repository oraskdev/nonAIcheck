"""Regression coverage for provider contracts, accounting and failure handling."""
import copy
import json
import time
import unittest
from unittest.mock import MagicMock, patch

import httpx

from app import bounded_patch as editing
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


if __name__ == "__main__":
    unittest.main()
