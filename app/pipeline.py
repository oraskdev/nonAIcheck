"""Bounded detector-guided revision; only measured provider results are reported."""
import math

from . import hygiene, providers


def text(blocks):
    return "\n\n".join(b["text"] for b in blocks)


def score(assessment):
    if assessment.get("status") != "assessed":
        return None
    value = assessment.get("ai_score", assessment.get("probabilities", {}).get("ai"))
    # Invalid estimates must never win selection or masquerade as a zero score.
    return value if (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and 0 <= value <= 1) else None


def run(blocks, options, progress):
    if options.get("writing_workflow") == "bounded-patch-v1":
        from .bounded_patch import run as bounded_run
        return bounded_run(blocks, options, progress)
    # Old stored quotes predate provider choice and consented only to GPTZero.
    provider = options.get("detector_provider") or "gptzero"
    name = "txtzi detector" if provider == "local" else "GPTZero"
    def measure(content, start, end):
        return providers.detect(text(content), provider=provider,
                                on_progress=lambda i, n: progress(start + int((end-start)*i/max(n, 1)), f"{name} · section {i+1}/{n}"))
    before = {"status": "not_assessed", "reason": "Detector comparison was not selected."}
    attempts = []
    if options.get("detector"):
        progress(7, f"{name} is measuring the original")
        before = measure(blocks, 7, 10)
        attempts.append({"version": "original", "assessment": before})
    baseline = hygiene.clean(blocks) if options.get("clean_hidden", True) else blocks
    revised, report = providers.refine(baseline, options, lambda p, s: progress(10 + int(p * .42), s))
    report = dict(report)
    all_usage = list(report.get("provider_usage", []))
    revision_reports = [{"version": "revision_1", **report}]
    if options.get("clean_hidden", True):
        revised = hygiene.clean(revised)
    after = {"status": "not_assessed", "reason": "Detector comparison was not selected."}
    selected = "revision_1"
    unavailable = False
    if options.get("detector"):
        progress(55, f"{name} is measuring the first revision")
        after = measure(revised, 55, 58)
        attempts.append({"version": selected, "assessment": after})
        unavailable = score(before) is None or score(after) is None
        if not unavailable:
            # Keep an untouched original as the fallback; never claim a lower unmeasured score.
            if baseline == blocks and score(before) <= score(after):
                revised, after, selected = blocks, before, "original"
                report = {"writing_method": "original-retained", "structure_recomposed": False, "flags": []}
            if score(after) > 0:
                retry_options = {**options, "depth": "thorough", "alternate_revision": True}
                try:
                    candidate, extra = providers.refine(baseline, retry_options, lambda p, s: progress(58 + int(p * .30), "Second revision · " + s), initial=revised)
                except providers.ProviderError as exc:
                    # A failed optional attempt must not discard a completed, measured result.
                    attempts.append({"version": "revision_2", "revision_error": str(exc), "assessment": {
                        "status": "not_assessed", "reason": "The second revision could not complete. The best completed version was retained."}})
                    unavailable = True
                else:
                    revision_reports.append({"version": "revision_2", **extra})
                    all_usage.extend(extra.get("provider_usage", []))
                    if options.get("clean_hidden", True):
                        candidate = hygiene.clean(candidate)
                    progress(91, f"{name} is comparing the second revision")
                    candidate_score = measure(candidate, 91, 99)
                    attempts.append({"version": "revision_2", "assessment": candidate_score})
                    if score(candidate_score) is None:
                        unavailable = True
                    elif score(candidate_score) < score(after):
                        revised, after, selected, report = candidate, candidate_score, "revision_2", dict(extra)
    improved = score(before) is not None and score(after) is not None and score(after) < score(before)
    report.update({
        "provider_usage": all_usage,
        "revision_reports": revision_reports,
        "before_detector": before,
        "after_detector": after,
        "detector_comparison": {"provider": name, "score_label": before.get("score_label", "AI-only class probability"), "selected_version": selected, "improved": improved, "attempts": attempts, "assessment_unavailable": unavailable, "notice": f"This comparison uses {name} only. A lower estimate does not establish human authorship or guarantee any other detector's result."},
        "hidden_character_audit": {"original": hygiene.audit(blocks), "output": hygiene.audit(revised), "cleanup_requested": options.get("clean_hidden", True)},
    })
    return revised, report
