import unittest
from unittest.mock import patch

from app import hygiene, pipeline


def assessment(ai):
    return {"status": "assessed", "provider": "GPTZero", "probabilities": {"ai": ai, "mixed": 0, "human": 1-ai}}


def revision(text):
    return ([{"id": "b0000", "type": "paragraph", "text": text}], {"provider_usage": [{"provider": "anthropic"}, {"provider": "openai"}, {"provider": "xai"}], "flags": []})


class PipelineTests(unittest.TestCase):
    def run_case(self, scores):
        source = revision("My original 30 minute plan.")[0]
        with patch("app.pipeline.providers.refine", side_effect=[revision("A first 30 minute plan."), revision("Another 30 minute plan.")]) as refine, patch("app.pipeline.providers.detect", side_effect=scores) as detect:
            result, report = pipeline.run(source, {"detector": True}, lambda *_: None)
            self.assertEqual(refine.call_count, 2)
            self.assertEqual(detect.call_count, 3)
        return result, report

    def test_keeps_lower_measured_revision(self):
        result, report = self.run_case([assessment(.9), assessment(.3), assessment(.6)])
        self.assertEqual(result[0]["text"], "A first 30 minute plan.")
        self.assertEqual(report["after_detector"]["probabilities"]["ai"], .3)
        self.assertTrue(report["detector_comparison"]["improved"])
        self.assertEqual(len(report["provider_usage"]), 6)

    def test_original_retained_when_both_candidates_score_worse(self):
        result, report = self.run_case([assessment(.1), assessment(.6), assessment(.5)])
        self.assertEqual(report["detector_comparison"]["selected_version"], "original")
        self.assertFalse(report["detector_comparison"]["improved"])
        self.assertEqual(result[0]["text"], "My original 30 minute plan.")

    def test_second_revision_selected_when_it_measures_lower(self):
        result, report = self.run_case([assessment(.9), assessment(.6), assessment(.2)])
        self.assertEqual(report["detector_comparison"]["selected_version"], "revision_2")
        self.assertEqual(result[0]["text"], "Another 30 minute plan.")

    def test_zero_estimate_stops_without_another_revision(self):
        with patch("app.pipeline.providers.refine", return_value=revision("Revised.")) as refine, patch("app.pipeline.providers.detect", side_effect=[assessment(.8), assessment(0)]) as detect:
            _, report = pipeline.run(revision("Original.")[0], {"detector": True}, lambda *_: None)
        self.assertEqual(refine.call_count, 1)
        self.assertEqual(detect.call_count, 2)
        self.assertTrue(report["detector_comparison"]["improved"])

    def test_failed_recheck_does_not_invent_a_score(self):
        result, report = self.run_case([assessment(.9), assessment(.4), {"status": "not_assessed"}])
        self.assertEqual(report["after_detector"]["probabilities"]["ai"], .4)
        self.assertTrue(report["detector_comparison"]["assessment_unavailable"])
        self.assertEqual(report["detector_comparison"]["attempts"][-1]["assessment"], {"status": "not_assessed"})

    def test_missing_detector_does_not_trigger_extra_paid_model_pass(self):
        with patch("app.pipeline.providers.refine", return_value=revision("Revised text.")) as refine, patch("app.pipeline.providers.detect", return_value={"status": "not_assessed"}):
            _, report = pipeline.run(revision("Original text.")[0], {"detector": True}, lambda *_: None)
        self.assertEqual(refine.call_count, 1)
        self.assertTrue(report["detector_comparison"]["assessment_unavailable"])
        self.assertFalse(report["detector_comparison"]["improved"])

    def test_hidden_cleanup_preserves_language_joiners_and_bidi(self):
        original = revision("\ufeffsoft\u00adhyphen\u2060 می\u200cروم \u200fשלום")[0]
        cleaned = hygiene.clean(original)
        self.assertEqual(hygiene.audit(original)["removable"], 3)
        self.assertEqual(hygiene.audit(cleaned)["removable"], 0)
        self.assertIn("\u200c", cleaned[0]["text"])
        self.assertIn("\u200f", cleaned[0]["text"])

    def test_cleanup_request_not_lost_to_original_fallback(self):
        source = revision("\ufeffOriginal.")[0]
        with patch("app.pipeline.providers.refine", side_effect=[revision("Revised."), revision("Alternative.")]), patch("app.pipeline.providers.detect", side_effect=[assessment(.1), assessment(.8), assessment(.9)]):
            result, report = pipeline.run(source, {"detector": True, "clean_hidden": True}, lambda *_: None)
        self.assertEqual(hygiene.audit(result)["removable"], 0)
        self.assertFalse(report["detector_comparison"]["improved"])


if __name__ == "__main__":
    unittest.main()
