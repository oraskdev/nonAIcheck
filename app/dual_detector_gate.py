"""Experimental two-detector selection gate; performs no inference or API calls.

This module is deliberately separate from the frozen single-detector experiments.
Neither customer quotes nor the production dispatcher select this version.
"""
import hashlib
import math

VERSION = "dual-detector-gate-v1"
DETECTORS = {
    "desklib": {"model": "desklib/ai-text-detector-v1.01",
                "revision": "5fdea974cd4287c61674951ec78803aa274e2fb7"},
    "vanguard": {"model": "ShantanuT01/vanguard-ai-text-detector",
                 "revision": "823061be63b90f2b42f64ac1e1f82772e872533b"},
}


class InvalidEvidence(ValueError):
    pass


def text_hash(text):
    if not isinstance(text, str) or not text.strip():
        raise InvalidEvidence("empty_or_invalid_text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def score_receipt(receipt, text_sha256, detector):
    """Require a fixed model, numeric estimate and full coverage of these exact bytes."""
    try:
        expected = DETECTORS[detector]
        value = receipt["measurement"]
        tokens = value["tokens_assessed"]
        number = value["ai_score"]
        if (receipt["sha256"] != text_sha256 or receipt["revision"] != expected["revision"]
                or value["model"] != expected["model"] or value.get("coverage") != "full_document"
                or not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0
                or not isinstance(number, (int, float)) or isinstance(number, bool)
                or not 0 <= number <= 1 or not math.isfinite(number)):
            raise InvalidEvidence("invalid_receipt_identity_or_score")
        if detector == "desklib":
            if (tokens > 40000 or value.get("status") != "assessed" or value.get("version") != expected["revision"]
                    or value.get("precision") != "bfloat16 matrix storage; float32 compute"):
                raise InvalidEvidence("desklib_protocol_mismatch")
            sections = value.get("sections")
            if not isinstance(sections, list) or not sections:
                raise InvalidEvidence("desklib_coverage_missing")
            expected_weights, start = [], 0
            while start < tokens:
                end = min(start + 510, tokens)
                expected_weights.append(end - start - (64 if start else 0))
                if end == tokens:
                    break
                start = end - 64
            if [section.get("weight") for section in sections] != expected_weights:
                raise InvalidEvidence("desklib_window_geometry_mismatch")
            for index, section in enumerate(sections, 1):
                weight, section_score = section.get("weight"), section.get("ai_score")
                if (isinstance(section.get("section"), bool) or section.get("section") != index
                        or not isinstance(weight, int) or isinstance(weight, bool)
                        or weight <= 0 or not isinstance(section_score, (int, float)) or isinstance(section_score, bool)
                        or not 0 <= section_score <= 1 or not math.isfinite(section_score)):
                    raise InvalidEvidence("desklib_section_invalid")
            if sum(s["weight"] for s in sections) != tokens or not math.isclose(
                    sum(s["weight"] * s["ai_score"] for s in sections) / tokens, number,
                    rel_tol=1e-12, abs_tol=1e-12):
                raise InvalidEvidence("desklib_coverage_or_aggregate_mismatch")
        # Existing pinned Vanguard research receipts omit a status field; every
        # identity/precision/coverage/value field remains mandatory below.
        elif (value.get("status", "assessed") != "assessed" or tokens > 8192
                or value.get("revision") != expected["revision"] or value.get("dtype") != "float32"
                or value.get("reference_compile") is not False or value.get("attention") != "sdpa"):
            raise InvalidEvidence("vanguard_protocol_mismatch")
        return number
    except (KeyError, TypeError, AttributeError) as exc:
        raise InvalidEvidence("missing_or_invalid_receipt") from exc


def source_approved(review, original_sha256, candidate_sha256, expected_atom_ids):
    """A score cannot override an incomplete or differently bound meaning review."""
    try:
        if not isinstance(expected_atom_ids, (list, tuple)):
            return False
        expected = list(expected_atom_ids)
        checked = review["checked_atom_ids"]
        return (bool(expected) and all(isinstance(a, str) and a for a in expected)
                and len(expected) == len(set(expected))
                and review["source_sha256"] == original_sha256
                and review["candidate_sha256"] == candidate_sha256
                and review["faithful"] is True and review["inventory_complete_and_supported"] is True
                and review["issues"] == [] and review["repairs"] == []
                and isinstance(checked, list) and all(isinstance(a, str) for a in checked)
                and len(checked) == len(set(checked)) and set(checked) == set(expected))
    except (KeyError, TypeError, AttributeError):
        return False


def choose(original_text, candidate_text, *, original_receipts, candidate_receipts,
           source_review, expected_atom_ids):
    """Accept only a faithful, fully assessed candidate that worsens neither detector.

    Comparisons are strict, with no post-hoc tolerance or average that can hide a
    worsening result. Equal scores on both detectors keep the unchanged original.
    Missing evidence fails closed and never triggers another provider request.
    """
    original_sha = text_hash(original_text)
    decision = {"workflow": VERSION, "accepted": False, "selected": "original",
                "selected_sha256": original_sha, "source_sha256": original_sha,
                "comparisons": {}, "reasons": [], "production_enabled": False}
    try:
        candidate_sha = text_hash(candidate_text)
    except InvalidEvidence as exc:
        decision["reasons"].append(str(exc))
        return decision
    decision["candidate_sha256"] = candidate_sha
    if not source_approved(source_review, original_sha, candidate_sha, expected_atom_ids):
        decision["reasons"].append("source_review_not_approved_or_not_bound")
    for detector in DETECTORS:
        try:
            before = score_receipt(original_receipts[detector], original_sha, detector)
            after = score_receipt(candidate_receipts[detector], candidate_sha, detector)
        except (KeyError, TypeError, InvalidEvidence) as exc:
            decision["reasons"].append(detector + ":invalid_or_missing_assessment")
            continue
        decision["comparisons"][detector] = {"original": before, "candidate": after,
                                               "change": after - before}
        if after > before:
            decision["reasons"].append(detector + ":worsened")
    if not decision["reasons"]:
        if candidate_sha == original_sha or not any(v["candidate"] < v["original"]
                                                    for v in decision["comparisons"].values()):
            decision["reasons"].append("no_measured_improvement")
        else:
            decision.update(accepted=True, selected="candidate", selected_sha256=candidate_sha)
    return decision
