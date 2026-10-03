"""Selection must keep the chosen document's metadata, not another attempt's."""
import unittest
from unittest.mock import patch

from app import hygiene, pipeline


def assessed(value):
    return {"status": "assessed", "provider_id": "local", "ai_score": value}


def blocks(*paragraphs):
    return [{"id": f"p{index}", "type": "paragraph", "text": text}
            for index, text in enumerate(paragraphs)]


def revision(content, method, recomposed, marker):
    return content, {
        "writing_method": method,
        "structure_recomposed": recomposed,
        "flags": [{"block_id": content[-1]["id"], "message": marker}],
        "provider_usage": [{"provider": name, "attempt_marker": marker}
                           for name in ("anthropic", "openai", "xai")],
    }


class PipelineSelectionTests(unittest.TestCase):
    def setUp(self):
        self.original = blocks("A project update.", "The meeting is on 12 October.")
        self.first = revision(
            blocks("First draft of the project update.", "The meeting is on 12 October."),
            "paragraph-edit-v1", False, "first correction",
        )
        self.second = revision(
            blocks("Second draft.", "A project update follows.", "The meeting is on 12 October."),
            "prose-recomposition-v1", True, "second correction",
        )

    def run_selection(self, scores):
        with patch("app.pipeline.providers.refine", side_effect=[self.first, self.second]), \
                patch("app.pipeline.providers.detect", side_effect=[assessed(s) for s in scores]):
            return pipeline.run(self.original, {"detector": True, "detector_provider": "local"}, lambda *_: None)

    def test_selected_second_revision_keeps_its_shape_and_metadata(self):
        result, report = self.run_selection((0.9, 0.7, 0.4))
        self.assertEqual(result, self.second[0])
        self.assertEqual(len(result), 3)
        self.assertEqual(report["writing_method"], "prose-recomposition-v1")
        self.assertIs(report["structure_recomposed"], True)
        self.assertEqual(report["flags"], self.second[1]["flags"])
        self.assertEqual(report["detector_comparison"]["selected_version"], "revision_2")
        self.assertEqual([u["attempt_marker"] for u in report["provider_usage"]],
                         ["first correction"] * 3 + ["second correction"] * 3)

    def test_retained_first_revision_does_not_inherit_rejected_attempt_metadata(self):
        result, report = self.run_selection((0.9, 0.3, 0.7))
        self.assertEqual(result, self.first[0])
        self.assertEqual(report["writing_method"], "paragraph-edit-v1")
        self.assertIs(report["structure_recomposed"], False)
        self.assertEqual(report["flags"], self.first[1]["flags"])
        self.assertEqual(len(report["provider_usage"]), 6)
        self.assertEqual(report["detector_comparison"]["selected_version"], "revision_1")

    def test_original_fallback_clears_revision_specific_metadata_but_keeps_usage(self):
        result, report = self.run_selection((0.1, 0.7, 0.4))
        self.assertEqual(result, self.original)
        self.assertEqual(report["writing_method"], "original-retained")
        self.assertIs(report["structure_recomposed"], False)
        self.assertEqual(report["flags"], [])
        self.assertEqual(len(report["provider_usage"]), 6)
        self.assertFalse(report["detector_comparison"]["improved"])
        self.assertEqual(report["detector_comparison"]["selected_version"], "original")

    def test_detector_scores_exact_post_review_cleaned_text_with_every_new_paragraph(self):
        # refine's contract is to return its final fidelity-reviewed blocks.
        # Cleanup must occur before measurement; language joiners must survive.
        first = revision(blocks("\ufeffReviewed first draft.", "12 October."),
                         "reviewed-v1", False, "first")
        second = revision(blocks("\ufeffReviewed second draft.", "The date is 12 October.",
                                 "soft\u00adhyphen\u2060 می\u200cروم"),
                          "recomposed-reviewed-v1", True, "second")
        with patch("app.pipeline.providers.refine", side_effect=[first, second]), \
                patch("app.pipeline.providers.detect", side_effect=[assessed(.9), assessed(.7), assessed(.2)]) as detect:
            result, report = pipeline.run(self.original,
                                         {"detector": True, "detector_provider": "local", "clean_hidden": True},
                                         lambda *_: None)
        measured = [call.args[0] for call in detect.call_args_list]
        self.assertEqual(measured, [pipeline.text(self.original), pipeline.text(hygiene.clean(first[0])),
                                    pipeline.text(hygiene.clean(second[0]))])
        self.assertEqual(measured[-1], pipeline.text(result))
        self.assertEqual(len(result), 3)
        self.assertIn("\u200c", measured[-1])
        self.assertEqual(hygiene.audit(result)["removable"], 0)
        self.assertEqual(report["after_detector"]["ai_score"], .2)

    def test_optional_second_provider_failure_keeps_completed_result_and_metadata(self):
        with patch("app.pipeline.providers.refine", side_effect=[self.second,
                    pipeline.providers.ProviderError("Retry unavailable")]), \
                patch("app.pipeline.providers.detect", side_effect=[assessed(.9), assessed(.3)]):
            result, report = pipeline.run(self.original,
                                         {"detector": True, "detector_provider": "local"}, lambda *_: None)
        self.assertEqual(result, self.second[0])
        self.assertEqual(report["writing_method"], "prose-recomposition-v1")
        self.assertIs(report["structure_recomposed"], True)
        self.assertEqual(report["flags"], self.second[1]["flags"])
        self.assertEqual(len(report["provider_usage"]), 3)
        self.assertEqual(len(report["revision_reports"]), 1)
        self.assertTrue(report["detector_comparison"]["assessment_unavailable"])
        self.assertEqual(report["detector_comparison"]["selected_version"], "revision_1")
        self.assertEqual(report["after_detector"]["ai_score"], .3)

    def test_invalid_second_score_cannot_replace_measured_first(self):
        for invalid in (False, -0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), \
                    patch("app.pipeline.providers.refine", side_effect=[self.first, self.second]), \
                    patch("app.pipeline.providers.detect", side_effect=[assessed(.9), assessed(.3), assessed(invalid)]):
                result, report = pipeline.run(self.original,
                                             {"detector": True, "detector_provider": "local"}, lambda *_: None)
            self.assertEqual(result, self.first[0])
            self.assertEqual(report["after_detector"]["ai_score"], .3)
            self.assertEqual(report["writing_method"], "paragraph-edit-v1")
            self.assertEqual(len(report["provider_usage"]), 6)
            self.assertTrue(report["detector_comparison"]["assessment_unavailable"])


if __name__ == "__main__":
    unittest.main()
