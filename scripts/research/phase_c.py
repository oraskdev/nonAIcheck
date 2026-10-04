"""Authorized fresh-original diagnostic with optional competitive-parent bank.

No paid call is possible without a separate coordinator approval bound to the
prospective plan. The existing global1.50 ledger reserves every request.
"""
import argparse
import itertools
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research import recovery as r
from scripts.research.phase_b import score_pair

C = r.RUN / "phase-c"
MAX_CALLS = 6
MAX_TEXTS = 151


def admitted():
    approval_path = C / "approval.json"
    if not approval_path.exists():
        raise RuntimeError("Phase C has not been authorized")
    approval = r.read(approval_path)
    plan = r.read(C / "plan-draft.json")
    digest = r.sha(json.dumps(plan, sort_keys=True))
    if (approval.get("authorized") is not True or approval.get("phase") != "C" or
        approval.get("max_new_calls") != MAX_CALLS or approval.get("max_new_distinct") != MAX_TEXTS or
        approval.get("global_budget_usd") != r.LIMIT_USD or approval.get("plan_sha256") != digest or
        approval.get("max_parent_score") != .35):
        raise ValueError("Phase C approval differs from its frozen scope")
    if r.cost(r.ledger()) > r.LIMIT_USD:
        raise RuntimeError("Global research budget exceeds limit")
    source, claims = r.bound_source()
    if plan["source_sha256"] != r.sha(source):
        raise ValueError("Phase C source identity differs")
    protocol = C / "protocol.json"
    if not protocol.exists():
        r.save(protocol, {**plan, "status": "activated", "activated_at": r.now(), "approval": approval,
            "phase_b_interim_status": r.read(r.RUN / "phase-b/status.json") if (r.RUN / "phase-b/status.json").exists() else None,
            "selection_context": "Fresh draft uses ORIGINAL only; B continues to its complete fixed count. Interim B status is recorded as context, never sent as score feedback to writers."})
    elif r.read(protocol).get("approval") != approval:
        raise ValueError("Activated Phase C approval changed")
    return source, claims


def call(provider, name, prompt, allow_api):
    admitted()  # Recheck the same bound coordinator approval before every request.
    request_id = "phase-c-" + name
    existing = r.ledger()["requests"]
    if request_id not in existing and len([k for k in existing if k.startswith("phase-c-")]) >= MAX_CALLS:
        raise RuntimeError("Phase C six-request limit reached")
    return r.call(provider, request_id, r.BASE_SYSTEM, json.dumps(prompt, ensure_ascii=False), allow_api)


def known_hashes():
    seen=set()
    for path in (r.RUN/"baseline.json",r.RUN/"source-original.json"):
        if path.exists(): seen.add(r.read(path)["sha256"])
    source, _ = r.bound_source()
    seen.add(r.sha(source))
    for directory in (r.RUN/"jobs",r.RUN/"phase-b/jobs",C/"jobs"):
        for path in directory.glob("*.json"): seen.add(r.read(path)["sha256"])
    for path in (r.RUN/"rounds").glob("*-bank.json"):
        seen.add(r.read(path)["parent"]["sha256"])
    historical=r.read(r.ROOT/"static/research-ten-trials.json")
    for j in [historical["original"],historical["baseline"],historical["selected"],*historical["trials"],*historical["repairs"]]:
        if j.get("sha256"): seen.add(j["sha256"])
    return seen


def check_text(text, source):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Missing full draft")
    text = text.strip()
    if (text.split("\n")[0] != source.split("\n")[0] or text.count(source.split("\n")[0]) != 1 or
        r.numbers(text) != r.numbers(source) or not r.clean(text)):
        raise ValueError("Full draft changed protected values or introduced disallowed characters")
    paragraphs = text.split("\n\n")
    if paragraphs[0] != source.split("\n")[0] or not 2 <= len(paragraphs)-1 <= 3:
        raise ValueError("Fresh draft must have exact title and two or three body paragraphs")
    return text


def initialize(allow_api):
    source, claims = admitted()
    path = C / "jobs/c00-draft.json"
    if path.exists() or (C/"duplicate-diagnostic.json").exists():
        print("Fresh draft already saved; preserving exact evidence")
        return
    context = {"original": source, "claims": claims}
    first = call("anthropic", "init-claude", {**context,
        "task": "Rewrite this entire personal note in2–3 coherent body paragraphs with a fresh natural structure. Preserve the exact title on its own first line and ALL32 source claims, including every condition, uncertainty, causal link, goal and timing. Use ordinary concrete phrasing and varied sentence lengths. No anecdotes, additional advice, theatrical personality, filler or manufactured disfluency. This is recomposition, not summarization. Return {text:complete_document} only."}, allow_api)
    if not isinstance(first.get("text"), str):
        raise ValueError("Claude returned no complete text")
    second = call("openai", "init-openai", {**context, "current_draft": first["text"],
        "task": "Compare the full draft with the original and all32 claims. Make ONLY necessary repairs of meaning drift, omissions, changed causal links, uncertainty, conditions, quantities or unsupported additions. Preserve the draft's fresh structure, natural voice and sentence variety; do not routinely polish it into a standard essay or restyle correct wording. Retain exact title and numeric literals. Return {text:complete_corrected_document}."}, allow_api)
    if not isinstance(second.get("text"), str):
        raise ValueError("OpenAI returned no complete text")
    third = call("xai", "init-grok", {**context, "current_draft": second["text"],
        "task": "Review the COMPLETE draft against the original and ALL32 claims. If necessary make minimal source-fidelity repairs, then assess your FINAL text, preserving the fresh structure and voice. Do not routinely restyle correct wording. Return {text:complete_final_document, faithful:boolean, checked_claim_ids:[all32IDs], issues:[unresolved_issue_strings]}. Set faithful true only when the final text preserves every source meaning, uncertainty, condition, causal relationship and scope without unsupported additions or serious prose defects."}, allow_api)
    text = check_text(third.get("text"), source)
    r.save(C / "initializer-review.json", third)
    if r.sha(text) in known_hashes():
        r.save(C/"duplicate-diagnostic.json",{"at":r.now(),"sha256":r.sha(text),"text":text,
            "new_unique":0,"status":"known_text_duplicate_not_a_new_test","retry":False})
        print("Fresh diagnostic returned a known text; preserved receipt, zero new unique tests, no retry")
        r.archive()
        return
    r.save(path, {"id": "c00-draft", "phase": "C", "text": text, "sha256": r.sha(text),
        "source_sha256": r.sha(source), "created_at": r.now(), "parent_id": "source-original",
        "parent_sha256": r.sha(source), "kind": "fresh_three_provider_full_rewrite",
        "provider_review_faithful": third.get("faithful") is True and not third.get("issues") and
          len(third.get("checked_claim_ids", [])) == 32 and set(third.get("checked_claim_ids", [])) == {c["id"] for c in claims},
        "combined_full_source_review": "pending"})
    r.save(C / "initialization-complete.json", {"at": r.now(), "fresh_drafts": 1,
        "next": "Exact full-text measurements and two independent source audits; optional bank only if eligible and maxscore<=0.35."})
    print("Fresh Phase C draft saved; detector and independent source reviews pending")
    r.archive()


def bank(allow_api):
    source, claims = admitted()
    if (C / "bank-complete.json").exists() or any((C / "jobs").glob("c01-*.json")):
        raise RuntimeError("Phase C bank already has evidence; no overwrite or implicit restart")
    parent = r.read(C / "jobs/c00-draft.json")
    if parent["sha256"] != r.sha(parent["text"]) or parent.get("source_sha256") != r.sha(source):
        raise ValueError("Fresh parent hash/source mismatch")
    pair = score_pair(parent["sha256"])
    if max(pair) > .35 or parent.get("provider_review_faithful") is not True:
        r.save(C / "admission-result.json", {"at": r.now(), "admitted": False,
            "reason": "Fresh parent was not competitive or failed provider whole-source review", "scores": pair})
        print("Phase C bank not admitted; no additional API calls")
        return
    reviewers = r.parent_approvals(parent, r.sha(source), claims)
    r.save(C / "admission-result.json", {"at": r.now(), "admitted": True, "scores": pair, "reviewers": reviewers})
    context = {"original": source, "claims": claims, "current": parent["text"]}
    proposed = call("anthropic", "bank-claude", {**context,
        "task": "Propose12–16 alternatives to different larger sentence spans or short paragraphs in this reviewed draft. Use meaningful sentence variety and everyday phrasing, with NO new facts, anecdotes, disfluency or invented personality. Each find is an exact unique20–850character contiguous span within a single paragraph; each replacement is15–1100characters, preserving EVERY claim and exact local may/might/should/would/could/must words. Keep title and numeric literals unchanged. Alternatives may overlap but will not be combined when they do. Return {patches:[{id,find,replace,reason}]}."}, allow_api)
    refined = call("openai", "bank-openai", {**context, "proposed": proposed,
        "task": "Refine this to12–16 faithful exact-span alternatives. Check every source qualification, condition, causal link and whole-source relationship. Preserve larger fresh sentence restructuring when correct; do not restore a formal template. Keep unique IDs, find spans20–850characters and replacements15–1100characters, no newlines, title/numbers/local uncertainty words unchanged. Return {patches:[{id,find,replace,reason}]}."}, allow_api)
    patches = []
    for item in refined.get("patches", []):
        if not isinstance(item.get("id"), str) or any(p["id"] == item["id"] for p in patches): continue
        p = r.valid_patch(parent["text"], item, max_find=850, max_replace=1100)
        if p: patches.append(p)
    review = call("xai", "bank-grok", {**context, "patches": patches,
        "task": "Review the complete CURRENT parent against ALL32 original source claims, then each patch independently when applied to this parent. Accept faithful rephrasing and reordered syntax; reject omission, changed conditions/uncertainty/causality, unsupported additions or serious prose defects. Return {baseline_faithful:boolean,baseline_issues:[string],checked_claim_ids:[all32IDs],patches:[{id,faithful:boolean,issues:[string]}]}. Do not rewrite patches."}, allow_api)
    r.save(C / "bank-review.json", review)
    if (review.get("baseline_faithful") is not True or review.get("baseline_issues") or
        len(review.get("checked_claim_ids", [])) != 32 or set(review["checked_claim_ids"]) != {c["id"] for c in claims}):
        raise ValueError("Phase C bank parent failed source review")
    rows = review.get("patches", [])
    checked = {p["id"]:p for p in rows}
    if len(checked) != len(rows) or set(checked) != {p["id"] for p in patches}:
        raise ValueError("Phase C patch review identity mismatch")
    patches = [p for p in patches if checked[p["id"]].get("faithful") is True and not checked[p["id"]].get("issues")]
    r.save(C / "bank.json", {"parent": parent, "patches": patches, "source_sha256": r.sha(source)})
    variants = [(i,) for i in range(len(patches))]
    pool = [x for width in (2,3,4) for x in itertools.combinations(range(len(patches)), width)]
    random.Random(6100403).shuffle(pool)
    variants += pool
    seen = known_hashes()
    made = []
    for indices in variants:
        chosen = sorted([patches[i] for i in indices], key=lambda p:p["start"])
        if any(a["end"] > b["start"] for a,b in zip(chosen, chosen[1:])): continue
        text = parent["text"]
        for p in reversed(chosen): text = text[:p["start"]]+p["replace"]+text[p["end"]:]
        text = check_text(text,source)
        digest = r.sha(text)
        if digest in seen: continue
        cid = f"c01-c{len(made)+1:03d}"
        path = C/"jobs"/(cid+".json")
        if path.exists(): raise RuntimeError("Refusing to replace a Phase C job")
        r.save(path,{"id":cid,"phase":"C","text":text,"sha256":digest,"source_sha256":r.sha(source),
            "parent_id":parent["id"],"parent_sha256":parent["sha256"],"patch_ids":[p["id"] for p in chosen],
            "created_at":r.now(),"combined_full_source_review":"pending","individual_patches_reviewed":True})
        seen.add(digest);made.append(cid)
        if len(made)>=150: break
    r.save(C/"bank-complete.json",{"at":r.now(),"accepted_patches":len(patches),"new_combinations":len(made),"candidate_ids":made,
                                      "maximum_phase_texts":MAX_TEXTS})
    print("Phase C bank generated",len(made),"new texts; exact measurements pending")
    r.archive()


def status(_allow_api=False):
    source,claims=r.bound_source()
    rows=[]
    for path in sorted((C/"jobs").glob("*.json")):
        job=r.read(path)
        if r.sha(job["text"])!=job["sha256"] or job.get("source_sha256")!=r.sha(source):
            raise ValueError("Phase C candidate text/source identity differs")
        try:d,v=score_pair(job["sha256"])
        except FileNotFoundError:continue
        try:reviewers=r.parent_approvals(job,r.sha(source),claims)
        except ValueError:reviewers=[]
        rows.append({"id":job["id"],"sha256":job["sha256"],"desklib":d,"vanguard":v,
            "maximum":max(d,v),"source_reviewers":reviewers,"review":"source_verified" if reviewers else "pending"})
    rows.sort(key=lambda x:x["maximum"])
    result={"at":r.now(),"phase":"C","unique_generated":len(list((C/"jobs").glob("*.json"))),
        "paired":len(rows),"new_provider_requests_attempted":sum(k.startswith("phase-c-") for k in r.ledger()["requests"]),
        "global_estimated_or_reserved_api_usd":r.cost(r.ledger()),"best":rows[:20],"scores":rows,
        "selected_verified":next((x for x in rows if x["review"]=="source_verified"),None)}
    for label,threshold in ((30,.30),(10,.10),(2,.02)):
        eligible=[x for x in rows if x["maximum"]<threshold and x["review"]=="source_verified"]
        result[f"verified_below_both_{label}"]=len(eligible)
        gate=C/f"verified-gate-{label}.json"
        if eligible and not gate.exists():
            selected=eligible[0]
            r.save(gate,{"at":r.now(),"phase":"C","selected":selected,"threshold":threshold,
                "job":r.read(C/"jobs"/(selected["id"]+".json")),
                "measurements":{d:r.read(r.RUN/"scores"/d/(selected["sha256"]+".json")) for d in ("desklib","vanguard")},
                "scope":"One-source adaptive result; no held-out or universal efficacy claim."})
    r.save(C/"status.json",result)
    print(json.dumps({k:v for k,v in result.items() if k!="scores"},indent=2))
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["initialize","bank","status"])
    p.add_argument("--allow-api",action="store_true")
    a=p.parse_args()
    globals()[a.action](a.allow_api)
