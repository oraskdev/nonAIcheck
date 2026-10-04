"""Experimental initialization only; no customer quote selects this version."""
import json

from . import bounded_patch as shared
from . import providers

VERSION = "bounded-draft-v1"
DRAFT_SCHEMA = shared.obj({"atoms": {"type": "array", "items": shared.ATOM},
    "paragraphs": {"type": "array", "items": shared.obj({"text": shared.S, "atom_ids": shared.STRINGS})}})
REVIEW_BANK_SCHEMA = shared.obj({**shared.REVIEW_SCHEMA["properties"],
                               "patches": {"type": "array", "items": shared.PATCH}})


def eligible(blocks):
    # Recomposition must not move text across internal section/layout anchors.
    return (shared.eligible(blocks) and any(b["type"] == "paragraph" for b in blocks)
            and all(b["type"] == "paragraph" for b in blocks[1:]))


def prepare(source, options, budget, progress):
    """One new draft, then independent whole-source approval and a small patch bank."""
    progress(15, "Claude is composing a fresh draft from the source meaning")
    response = budget.call("anthropic", shared.TRUST +
        "Return a complete source-linked inventory and one fresh full draft. Do not merely replace synonyms "
        "in the source sentences. Let the source's actual purpose determine the order and grouping of its "
        "thoughts. Preserve its language, genre, point of view and degree of certainty; do not invent a "
        "different audience, personality or experience. Use ordinary precise prose appropriate to that "
        "document. Do not add framing or a summary just to sound polished. Preserve every substantive "
        "point, condition, causal relationship, attribution, quotation, numeric literal and URL. "
        "Atoms contain id, statement and original source_ids. Cover all source body paragraphs. The "
        "paragraphs contain text and atom_ids; every atom must be expressed. You may choose new paragraph "
        "boundaries and order. Do not add headings; the app preserves the existing title separately. "
        "Return JSON matching the provided schema.",
        {"source": source, "tone": options.get("tone", "natural")}, DRAFT_SCHEMA)
    body = [b for b in source if b["type"] == "paragraph"]
    heading_ids = {b["id"] for b in source if b["type"] == "heading"}
    try:
        atoms = response["atoms"]
        # A supplied title atom need not be written as a new body paragraph.
        body_atoms = [a for a in atoms if set(a["source_ids"]) - heading_ids]
        plan = providers.parse_recomposition_plan(json.dumps({"genre": "source genre", "voice": "source voice",
                                                              "atoms": body_atoms}), body)
        run_id = "bounded-draft"
        while any(b["id"].startswith(run_id + "-") for b in source):
            run_id += "x"
        paragraphs, _ = providers.parse_recomposition_draft(json.dumps({"paragraphs": response["paragraphs"]}), body, plan, run_id)
        draft = [b for b in source if b["type"] == "heading"] + paragraphs
        failure = providers.validate_recomposition(source, draft)
        if failure:
            raise ValueError(failure)
        inventory = shared.validate_bank({"atoms": atoms, "patches": []}, source)
    except (ValueError, TypeError, KeyError, providers.ProviderError) as exc:
        raise providers.ProviderError("The fresh draft failed source structure checks. Your payment will be returned.") from exc
    progress(25, "OpenAI is comparing the entire fresh draft with the original")
    verdict = budget.call("openai", shared.TRUST +
        "Compare the complete candidate with the complete authoritative original in BOTH directions. "
        "Verify the inventory is complete and supported, every original substantive point survives, and "
        "every candidate claim has source support. Specifically retain intentions versus actions, "
        "uncertainty, conditions and causal relationships. Equivalent wording and paragraph order are "
        "acceptable; stylistic preference is not a meaning discrepancy. Copy source_sha256 and "
        "candidate_sha256 exactly and list every checked atom ID. Set faithful=true only for a fully "
        "faithful candidate; report every issue otherwise. Do not repair or silently approve a flawed "
        "candidate: repairs must be empty. If faithful, also propose up to 12 independent, nonoverlapping "
        "exact-span wording improvements against the CANDIDATE, using its block IDs. Keep the same "
        "source meaning, numeric literals and modal verbs. Each find must occur once, be 8–600 characters, "
        "and its replacement at most 900. Do not force edits or introduce generic transitions, conclusions "
        "or filler. Leave headings unchanged. Return an empty patches list if the candidate is not faithful. "
        "Return JSON matching the supplied schema.",
        {"source": source, "candidate": draft, "inventory": inventory["atoms"],
         "source_sha256": shared.digest(source), "candidate_sha256": shared.digest(draft)}, REVIEW_BANK_SCHEMA)
    info = {"status": "rejected", "source_sha256": shared.digest(source),
            "draft_sha256": shared.digest(draft), "review": verdict}
    try:
        approved = shared.validate_review(verdict, source, draft, inventory)
    except providers.ProviderError:
        approved = False
    if not approved:
        return source, inventory, info
    bank = shared.validate_bank({"atoms": inventory["atoms"], "patches": verdict.get("patches")}, source, patch_source=draft)
    info["status"] = "accepted"
    return draft, bank, info
