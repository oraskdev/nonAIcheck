"""Prospective no-API expansion of frozen patch banks; activation is separate.

No command can generate jobs before phase A has1000 fully measured texts and
the coordinator creates phase-b/approval.json authorizing named banks.
Predicted logit ranks choose tests; only exact inference supplies measurements.
"""
import argparse
import contextlib
import io
import itertools
import json
import math
from pathlib import Path
import random
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r

B = r.RUN / "phase-b"
CAP = 1000
SEED = 6100402
BEAM = 3000


def sigmoid(value):
    return 1 / (1 + math.exp(-max(-50, min(50, value))))


def logit(value):
    value = max(1e-7, min(1-1e-7, value))
    return math.log(value / (1-value))


def score_pair(digest):
    pair = []
    for detector, revision in (("desklib", r.DESK_REV), ("vanguard", r.VANG_REV)):
        record = r.read(r.RUN / "scores" / detector / (digest + ".json"))
        r.validate_score(record, digest, detector, revision)
        pair.append(record["measurement"]["ai_score"])
    return pair


def apply(parent, patches):
    ordered = sorted(patches, key=lambda p: p["start"])
    if any(a["end"] > b["start"] for a, b in zip(ordered, ordered[1:])):
        return None
    text = parent
    for p in reversed(ordered):
        if text[p["start"]:p["end"]] != p["find"]:
            raise ValueError("Patch span identity changed")
        text = text[:p["start"]] + p["replace"] + text[p["end"]:]
    return text


def prepare():
    path = B / "plan-draft.json"
    if path.exists():
        print("Prospective draft already exists; retained unchanged")
        return
    r.save(path, {"created_at": r.now(), "status": "prospective_not_activated", "phase": "B",
        "prerequisites": "Phase A completed1000 distinct exact dual measurements, final source review; separate coordinator authorization naming selected banks required before generating B jobs.",
        "maximum_new_distinct_texts": CAP, "paid_provider_calls": 0, "shared_total_api_cap_usd": r.LIMIT_USD,
        "bank_selection": "Use two strongest existing banks by their two-source-reviewed parent's larger exact detector score; coordinator names banks after phase A. Do not populate B from weak early parents merely to fill count.",
        "ranking": "For each approved patch, measure its single-patch full text at fixed checkpoints. Estimate a combination's two logits by adding single-patch logit differences to parent logits. Rank by max predicted logit; predictions are not measured scores.",
        "combinations": "Enumerate nonoverlapping2–8 patch combinations with deterministic beam width3000. Keep top rank candidates plus a fixed seeded diversity sample from unused retained candidates.",
        "sampling": "Up to750 best-ranked plus250 seeded alternatives; if duplicates/history exclusion removes rows, continue best-ranked unused combinations until at most1000 unique new texts.",
        "seed": SEED, "beam_width": BEAM, "exclude": "Every known historical ten-trial, phase A, source, parent and existing phase B text hash.",
        "guards": "Exact valid spans, protected numeric literals, title, local modal words, no hidden/control characters; unchanged three-provider patch approvals.",
        "measurements": "New exact full-text Desklib+Vanguard inference at same model revisions and precisions. Never treat predicted ranks or another text's measurement as a score.",
        "eligibility": "Two distinct complete hash-bound32claim and whole-source/quality approvals for exact measured candidate before threshold promotion.",
        "targets": [.10, .02], "phase_separation": "B counts and estimates reported separately; retains phase A immutable cap and findings.",
        "limitations": "One source; both detectors used for adaptive selection; zero held-out evidence or universal detector/watermark guarantee."})
    print("Prospective phase B draft saved; no generation or API calls")


def bank_ranked(bank_id):
    bank = r.read(r.RUN / "rounds" / (bank_id + "-bank.json"))
    parent = bank["parent"]
    source, claims = r.bound_source()
    if parent["sha256"] != r.sha(parent["text"]) or parent.get("source_sha256") != r.sha(source):
        raise ValueError("Bank parent identity differs")
    r.parent_approvals(parent, r.sha(source), claims)
    parent_logits = list(map(logit, score_pair(parent["sha256"])))
    patches, deltas = [], []
    review = r.read(r.RUN / "rounds" / (bank_id + "-review.json"))
    if (review.get("baseline_faithful") is not True or review.get("baseline_issues") or
        len(review.get("checked_claim_ids", [])) != 32 or set(review["checked_claim_ids"]) != {c["id"] for c in claims}):
        raise ValueError("Bank source review is incomplete or failed")
    submitted = r.read(r.RUN / "rounds" / (bank_id + "-grok.request.json"))
    prompt = json.loads(submitted["prompt"])
    if (submitted.get("provider") != "xai" or submitted.get("model") != r.MODELS["xai"] or
        prompt.get("source") != source or prompt.get("current") != parent["text"] or prompt.get("claims") != claims):
        raise ValueError("Saved reviewer request is not bound to this source and parent")
    submitted_patches = {p["id"]: p for p in prompt["patches"]}
    if len(submitted_patches) != len(prompt["patches"]):
        raise ValueError("Saved reviewer request contains duplicate patch identities")
    receipt = r.read(r.RUN / "rounds" / (bank_id + "-grok.response.json"))
    body = receipt["body"]
    if receipt["http_status"] != 200 or body.get("status") != "completed" or body.get("incomplete_details"):
        raise ValueError("Saved review receipt is not complete")
    output = "".join(c.get("text", "") for item in body.get("output", []) for c in item.get("content", []) if c.get("type") == "output_text")
    actual_review = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", output.strip()))
    if actual_review != review:
        raise ValueError("Review JSON differs from saved provider response")
    approved = {p["id"] for p in review["patches"] if p.get("faithful") is True and not p.get("issues")}
    for p in bank["patches"]:
        validated = r.valid_patch(parent["text"], p)
        if validated != p or p["id"] not in approved or submitted_patches.get(p["id"]) != p:
            raise ValueError("Bank patch no longer valid or approved")
        single_text = apply(parent["text"], [p])
        values = score_pair(r.sha(single_text))
        patches.append(p)
        deltas.append([logit(x)-base for x, base in zip(values, parent_logits)])
    states = [((), tuple(parent_logits))]
    ranked = []
    for width in range(1, 9):
        expanded = []
        for indices, values in states:
            for i in range(indices[-1]+1 if indices else 0, len(patches)):
                p = patches[i]
                if any(not (p["end"] <= patches[j]["start"] or p["start"] >= patches[j]["end"]) for j in indices):
                    continue
                new = indices + (i,)
                predicted = tuple(x+d for x, d in zip(values, deltas[i]))
                expanded.append((new, predicted))
        expanded.sort(key=lambda x: (max(x[1]), sum(x[1]), x[0]))
        states = expanded[:BEAM]
        if width >= 2:
            ranked += [{"bank": bank_id, "indices": indices, "predicted_logits": values,
                        "predicted_rank_key": max(values)} for indices, values in states]
    ranked.sort(key=lambda x: (x["predicted_rank_key"], x["bank"], x["indices"]))
    return bank, patches, ranked


def generate():
    approval_path = B / "approval.json"
    if not approval_path.exists():
        raise RuntimeError("Phase B requires coordinator authorization after phase A")
    approval = r.read(approval_path)
    if approval.get("authorized") is not True or approval.get("phase") != "B" or approval.get("max_new_unique") != CAP:
        raise ValueError("Invalid phase B activation record")
    if any((B / "jobs").glob("*.json")) or (B / "complete.json").exists():
        raise RuntimeError("Phase B already has evidence; refusing replacement or implicit restart")
    with contextlib.redirect_stdout(io.StringIO()):
        phase_a = r.status()
    if phase_a["unique_generated"] != 1000 or phase_a["paired"] != 1000 or not phase_a["selected_verified"]:
        raise RuntimeError("Phase A is not complete and source reviewed")
    if len({r.read(p)["sha256"] for p in (r.RUN / "jobs").glob("*.json")}) != 1000:
        raise ValueError("Phase A does not contain1000 distinct text identities")
    if r.cost(r.ledger()) > r.LIMIT_USD:
        raise RuntimeError("Global research budget already exceeds cap")
    banks = approval.get("banks")
    if not isinstance(banks, list) or len(banks) != 2 or len(set(banks)) != 2:
        raise ValueError("Coordinator must select two distinct reviewed banks")
    source, claims = r.bound_source()
    gathered, lookup = [], {}
    for name in banks:
        if not isinstance(name, str) or not name.startswith("r") or not name[1:].isdigit():
            raise ValueError("Invalid bank identifier")
        bank, patches, ranked = bank_ranked(name)
        lookup[name] = (bank, patches)
        gathered.extend(ranked)
    gathered.sort(key=lambda x: (x["predicted_rank_key"], x["bank"], x["indices"]))
    seen = {r.sha(source)}
    for path in (r.RUN / "jobs").glob("*.json"):
        seen.add(r.read(path)["sha256"])
    historical = r.read(r.ROOT / "static/research-ten-trials.json")
    for row in [historical["original"], historical["baseline"], historical["selected"], *historical["trials"], *historical["repairs"]]:
        if row.get("sha256"): seen.add(row["sha256"])
    seen.update(bank["parent"]["sha256"] for bank, _ in lookup.values())
    candidates = []
    for row in gathered:
        bank, patches = lookup[row["bank"]]
        chosen = [patches[i] for i in row["indices"]]
        text = apply(bank["parent"]["text"], chosen)
        if text is None: continue
        digest = r.sha(text)
        if digest in seen: continue
        if (r.numbers(text) != r.numbers(source) or not r.clean(text) or
            text.split("\n")[0] != source.split("\n")[0] or text.count(source.split("\n")[0]) != 1):
            raise ValueError("Phase B combination failed protected-value/Unicode/title checks")
        seen.add(digest)
        candidates.append({"text": text, "sha256": digest, "source_sha256": r.sha(source),
            "parent_id": bank["parent"]["id"], "parent_sha256": bank["parent"]["sha256"],
            "bank": row["bank"], "patch_ids": [p["id"] for p in chosen],
            "ranking_only_predicted_logits": row["predicted_logits"], "prediction_is_not_a_measurement": True})
    primary = candidates[:750]
    remainder = candidates[750:]
    random.Random(SEED).shuffle(remainder)
    selected = primary + remainder[:250]
    if len(selected) < CAP:
        hashes = {c["sha256"] for c in selected}
        selected += [c for c in candidates if c["sha256"] not in hashes][:CAP-len(selected)]
    r.save(B / "phase-a-final-status.json", phase_a)
    protocol = {**r.read(B / "plan-draft.json"), "status": "activated", "activated_at": r.now(),
                "approval": approval, "phase_a_status_sha256": r.sha(json.dumps(phase_a, sort_keys=True)),
                "frozen_banks": banks, "frozen_bank_file_sha256": {
                    f"{bank}-{suffix}.json": r.sha((r.RUN / "rounds" / f"{bank}-{suffix}.json").read_text())
                    for bank in banks for suffix in ("bank", "review", "grok.request", "grok.response")},
                "new_api_calls": 0}
    r.save(B / "protocol.json", protocol)
    for index, c in enumerate(selected, 1):
        c.update({"id": f"b01-c{index:04d}", "phase": "B", "created_at": r.now(),
                  "combined_full_source_review": "pending", "individual_patches_reviewed": True})
        r.save(B / "jobs" / (c["id"] + ".json"), c)
    r.save(B / "complete.json", {"at": r.now(), "unique_generated": len(selected), "ranked_unused_pool": len(candidates),
                                "bank_names": banks, "new_api_calls": 0, "scoring": "pending"})
    print("Phase B generated", len(selected), "distinct texts; no API calls; measurements pending")
    r.archive()


def status():
    source, claims = r.bound_source()
    rows = []
    for p in sorted((B / "jobs").glob("*.json")):
        job = r.read(p)
        if r.sha(job["text"]) != job["sha256"] or job.get("source_sha256") != r.sha(source):
            raise ValueError("Phase B text/source identity differs")
        try: d, v = score_pair(job["sha256"])
        except FileNotFoundError: continue
        try: reviewers = r.parent_approvals(job, r.sha(source), claims)
        except ValueError: reviewers = []
        rows.append({"id": job["id"], "sha256": job["sha256"], "desklib": d, "vanguard": v,
                     "maximum": max(d, v), "source_reviewers": reviewers,
                     "review": "source_verified" if reviewers else "pending"})
    rows.sort(key=lambda x: x["maximum"])
    result = {"at": r.now(), "phase": "B", "unique_generated": len(list((B / "jobs").glob("*.json"))),
              "paired": len(rows), "new_api_calls": 0, "best": rows[:20], "scores": rows,
              "selected_verified": next((x for x in rows if x["review"] == "source_verified"), None),
              "global_estimated_or_reserved_api_usd": r.cost(r.ledger())}
    for label, threshold in ((30, .30), (10, .10), (2, .02)):
        eligible = [x for x in rows if x["maximum"] < threshold and x["review"] == "source_verified"]
        result[f"verified_below_both_{label}"] = len(eligible)
        if eligible and not (B / f"verified-gate-{label}.json").exists():
            selected = eligible[0]
            r.save(B / f"verified-gate-{label}.json", {"at": r.now(), "phase": "B", "selected": selected,
                "job": r.read(B / "jobs" / (selected["id"] + ".json")), "threshold": threshold,
                "measurements": {d: r.read(r.RUN / "scores" / d / (selected["sha256"] + ".json")) for d in ("desklib", "vanguard")},
                "scope": "Exact selected one-source in-sample result; not universal or held-out evidence."})
    r.save(B / "status.json", result)
    print(json.dumps({k:v for k,v in result.items() if k != "scores"}, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["prepare", "generate", "status"])
    a = p.parse_args()
    globals()[a.action]()
