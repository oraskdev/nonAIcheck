"""Bounded detector-guided revision; only measured provider results are reported."""
from . import hygiene, providers


def text(blocks):
    return "\n\n".join(b["text"] for b in blocks)


def score(assessment):
    if assessment.get("status") != "assessed":
        return None
    return assessment["probabilities"]["ai"]


def run(blocks, options, progress):
    before = {"status": "not_assessed", "reason": "Detector comparison was not selected."}
    attempts = []
    if options.get("detector"):
        progress(7, "GPTZero is measuring the original")
        before = providers.detect(text(blocks))
        attempts.append({"version": "original", "assessment": before})
    baseline = hygiene.clean(blocks) if options.get("clean_hidden", True) else blocks
    revised, report = providers.refine(baseline, options, lambda p, s: progress(10 + int(p * .42), s))
    if options.get("clean_hidden", True):
        revised = hygiene.clean(revised)
    after = {"status": "not_assessed", "reason": "Detector comparison was not selected."}
    selected = "revision_1"
    unavailable = False
    if options.get("detector"):
        progress(55, "GPTZero is measuring the first revision")
        after = providers.detect(text(revised))
        attempts.append({"version": selected, "assessment": after})
        unavailable = score(before) is None or score(after) is None
        if not unavailable:
            # Keep an untouched original as the fallback; never claim a lower unmeasured score.
            if baseline == blocks and score(before) <= score(after):
                revised, after, selected = blocks, before, "original"
            if score(after) > 0:
                retry_options = {**options, "depth": "thorough", "alternate_revision": True}
                candidate, extra = providers.refine(baseline, retry_options, lambda p, s: progress(58 + int(p * .30), "Second revision · " + s), initial=revised)
                if options.get("clean_hidden", True):
                    candidate = hygiene.clean(candidate)
                progress(91, "GPTZero is comparing the second revision")
                candidate_score = providers.detect(text(candidate))
                attempts.append({"version": "revision_2", "assessment": candidate_score})
                report["provider_usage"].extend(extra["provider_usage"])
                report["flags"].extend(extra["flags"])
                if score(candidate_score) is None:
                    unavailable = True
                elif score(candidate_score) < score(after):
                    revised, after, selected = candidate, candidate_score, "revision_2"
    improved = score(before) is not None and score(after) is not None and score(after) < score(before)
    report.update({
        "before_detector": before,
        "after_detector": after,
        "detector_comparison": {"selected_version": selected, "improved": improved, "attempts": attempts, "assessment_unavailable": unavailable, "notice": "This comparison uses GPTZero only. A lower AI estimate does not establish human authorship or guarantee any other detector's result."},
        "hidden_character_audit": {"original": hygiene.audit(blocks), "output": hygiene.audit(revised), "cleanup_requested": options.get("clean_hidden", True)},
    })
    return revised, report
