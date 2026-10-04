import copy
import unittest

from app import dual_detector_gate as gate


def receipt(detector, text, score):
    specification = gate.DETECTORS[detector]
    measurement = {"status": "assessed", "model": specification["model"],
        "ai_score": score, "tokens_assessed": 100, "coverage": "full_document"}
    if detector == "desklib":
        measurement.update(version=specification["revision"], precision="bfloat16 matrix storage; float32 compute",
                           sections=[{"section": 1, "weight": 100, "ai_score": score}])
    else:
        measurement.update(revision=specification["revision"], dtype="float32", reference_compile=False, attention="sdpa")
    return {"sha256": gate.text_hash(text), "revision": specification["revision"], "measurement": measurement}


class DualDetectorGateTests(unittest.TestCase):
    def setUp(self):
        self.original = "The original wording may describe a proposed update."
        self.candidate = "The proposed update may be described in different wording."
        self.before = {d: receipt(d, self.original, .6) for d in gate.DETECTORS}
        self.after = {d: receipt(d, self.candidate, .2) for d in gate.DETECTORS}
        self.review = {"source_sha256": gate.text_hash(self.original), "candidate_sha256": gate.text_hash(self.candidate),
            "faithful": True, "inventory_complete_and_supported": True, "issues": [], "repairs": [], "checked_atom_ids": ["a1"]}

    def decide(self):
        return gate.choose(self.original, self.candidate, original_receipts=self.before,
                           candidate_receipts=self.after, source_review=self.review, expected_atom_ids=["a1"])

    def test_both_improve_accepts_exact_candidate(self):
        result = self.decide()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["selected_sha256"], gate.text_hash(self.candidate))
        self.assertFalse(result["production_enabled"])

    def test_frozen_holdout_score_pattern_rejects_vanguard_worsening(self):
        # Exact aggregate receipts from the prospective test; no private source text is copied here.
        self.before["desklib"] = receipt("desklib", self.original, .2112809121608734)
        self.after["desklib"] = receipt("desklib", self.candidate, .1599419116973877)
        self.before["vanguard"]["measurement"]["ai_score"] = .3685223460197449
        self.after["vanguard"]["measurement"]["ai_score"] = .9994981288909912
        result = self.decide()
        self.assertFalse(result["accepted"])
        self.assertEqual(result["selected_sha256"], gate.text_hash(self.original))
        self.assertEqual(result["reasons"], ["vanguard:worsened"])

    def test_worsening_either_detector_cannot_be_hidden_by_improving_average(self):
        for detector in gate.DETECTORS:
            with self.subTest(detector=detector):
                self.after = {d: receipt(d, self.candidate, 0) for d in gate.DETECTORS}
                self.after[detector] = receipt(detector, self.candidate, .600000000001)
                self.assertFalse(self.decide()["accepted"])

    def test_equal_scores_retain_original_but_one_strict_improvement_can_pass(self):
        for detector in gate.DETECTORS:
            self.after[detector] = receipt(detector, self.candidate, .6)
        self.assertFalse(self.decide()["accepted"])
        self.after["desklib"] = receipt("desklib", self.candidate, .59)
        self.assertTrue(self.decide()["accepted"])

    def test_missing_invalid_or_partial_scores_fail_closed(self):
        for bad in [None, True, float("nan"), float("inf"), -.1, 1.1]:
            with self.subTest(score=bad):
                self.after["vanguard"]["measurement"]["ai_score"] = bad
                self.assertFalse(self.decide()["accepted"])
        self.after["vanguard"] = receipt("vanguard", self.candidate, .2)
        self.after["vanguard"]["measurement"]["coverage"] = "truncated"
        self.assertFalse(self.decide()["accepted"])
        del self.after["vanguard"]
        self.assertFalse(self.decide()["accepted"])

    def test_hash_model_revision_and_precision_are_bound(self):
        bad_receipts = []
        for key, value in [("sha256", gate.text_hash(self.original)), ("revision", "other revision")]:
            item = copy.deepcopy(self.after); item["vanguard"][key] = value; bad_receipts.append(item)
        for key, value in [("model", "other model"), ("dtype", "bfloat16"), ("reference_compile", True), ("tokens_assessed", 8193)]:
            item = copy.deepcopy(self.after); item["vanguard"]["measurement"][key] = value; bad_receipts.append(item)
        for item in bad_receipts:
            self.after = item
            self.assertFalse(self.decide()["accepted"])

    def test_bad_source_review_cannot_be_overridden_by_scores(self):
        for changes in [{"faithful": False}, {"candidate_sha256": "other text"},
                        {"checked_atom_ids": []}, {"checked_atom_ids": ["a1", "a1"]},
                        {"inventory_complete_and_supported": False}, {"issues": ["Lost qualification"]}]:
            with self.subTest(changes=changes):
                saved = self.review
                self.review = {**saved, **changes}
                self.assertFalse(self.decide()["accepted"])
                self.review = saved

    def test_desklib_sections_must_cover_exact_token_count_and_reproduce_score(self):
        self.after["desklib"]["measurement"]["sections"][0]["weight"] = 99
        self.assertFalse(self.decide()["accepted"])
        self.after["desklib"]["measurement"]["sections"][0]["weight"] = 100
        self.after["desklib"]["measurement"]["sections"][0]["ai_score"] = .3
        self.assertFalse(self.decide()["accepted"])

    def test_desklib_window_geometry_and_token_limit_are_fixed(self):
        measurement = self.after["desklib"]["measurement"]
        for tokens, weights in [(1000, [1000]), (511, [509, 2]),
                                (600, [500, 100]), (40001, [40001])]:
            with self.subTest(tokens=tokens, weights=weights):
                measurement["tokens_assessed"] = tokens
                measurement["sections"] = [{"section": index, "weight": weight, "ai_score": .2}
                                           for index, weight in enumerate(weights, 1)]
                self.assertFalse(self.decide()["accepted"])
        measurement["tokens_assessed"] = 511
        measurement["sections"] = [{"section": 1, "weight": 510, "ai_score": .2},
                                   {"section": 2, "weight": 1, "ai_score": .2}]
        measurement["ai_score"] = sum(s["weight"] * s["ai_score"] for s in measurement["sections"]) / 511
        self.assertTrue(self.decide()["accepted"])

    def test_extremely_large_integer_scores_fail_closed_without_overflow(self):
        for detector in gate.DETECTORS:
            with self.subTest(detector=detector):
                saved = copy.deepcopy(self.after)
                self.after[detector]["measurement"]["ai_score"] = 10 ** 1000
                self.assertFalse(self.decide()["accepted"])
                self.after = saved

    def test_boolean_section_index_is_not_an_integer_protocol_index(self):
        self.after["desklib"]["measurement"]["sections"][0]["section"] = True
        self.assertFalse(self.decide()["accepted"])

    def test_expected_inventory_string_is_not_a_list_of_atom_ids(self):
        self.review["checked_atom_ids"] = ["a", "1"]
        self.assertFalse(gate.source_approved(self.review, gate.text_hash(self.original),
                                             gate.text_hash(self.candidate), "a1"))


if __name__ == "__main__":
    unittest.main()
